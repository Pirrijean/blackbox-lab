"""Durable, conservative budget accounting.

Reservations are made before an adapter call. A reservation for an uncertain
request is intentionally never released: spending and the remote side effect
are unknown, so reusing that allowance would make the advertised ceiling
meaningless.
"""

from __future__ import annotations

import os
import tempfile
import threading
import time
import uuid
from contextlib import contextmanager
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Iterator

from pydantic import BaseModel, ConfigDict, Field


class BudgetExceededError(Exception):
    """The authorised call or its reconciled cost exceeds the protocol."""


class BudgetState(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    limit_usd: str
    confirmed_spend_usd: str
    reserved_spend_usd: str
    max_calls: int
    calls_completed: int
    max_output_tokens: int
    tokens_consumed: int
    reservations: dict[str, str] = Field(default_factory=dict)
    breached: bool = False


class BudgetManager:
    """A fail-closed ledger with a small cross-process lock.

    The lock serialises the load-modify-store sequence. It is intentionally a
    local accounting control; a provider-side cap is still required to impose a
    billing ceiling outside this process.
    """

    def __init__(
        self,
        limit_usd: Decimal | str | float = Decimal("0"),
        max_calls: int = 1,
        max_output_tokens: int = 100_000,
        storage_path: Path | str | None = None,
    ):
        self.limit_usd = self._amount(limit_usd)
        self.max_calls = int(max_calls)
        self.max_output_tokens = int(max_output_tokens)
        if self.max_calls <= 0 or self.max_output_tokens < 0:
            raise ValueError("Límites de presupuesto inválidos.")

        self.storage_path = Path(storage_path).resolve() if storage_path else None
        self._thread_lock = threading.RLock()
        self.confirmed_spend_usd = Decimal("0")
        self.reserved_spend_usd = Decimal("0")
        self.calls_completed = 0
        self.tokens_consumed = 0
        self.reservations: dict[str, Decimal] = {}
        self.breached = False

        if self.storage_path and self.storage_path.exists():
            self._load_state()

    @staticmethod
    def _amount(value: Decimal | str | float) -> Decimal:
        try:
            amount = Decimal(str(value))
        except (InvalidOperation, ValueError) as exc:
            raise ValueError("Importe monetario inválido.") from exc
        if not amount.is_finite() or amount < 0:
            raise ValueError("El importe debe ser finito y no negativo.")
        return amount

    @property
    def remaining_budget_usd(self) -> Decimal:
        return max(
            Decimal("0"),
            self.limit_usd - self.confirmed_spend_usd - self.reserved_spend_usd,
        )

    @contextmanager
    def _exclusive_lock(self) -> Iterator[None]:
        """Take an O_EXCL lock that works across local Python processes."""
        if self.storage_path is None:
            yield
            return

        self.storage_path.parent.mkdir(parents=True, exist_ok=True)
        lock_path = self.storage_path.with_suffix(self.storage_path.suffix + ".lock")
        deadline = time.monotonic() + 5.0
        descriptor: int | None = None
        while descriptor is None:
            try:
                descriptor = os.open(lock_path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
                os.write(descriptor, str(os.getpid()).encode("ascii"))
            except FileExistsError:
                if time.monotonic() >= deadline:
                    raise BudgetExceededError("El ledger está ocupado; se bloquea por seguridad.")
                time.sleep(0.05)

        try:
            yield
        finally:
            os.close(descriptor)
            try:
                lock_path.unlink()
            except FileNotFoundError:
                pass

    def _refresh_locked(self) -> None:
        if self.storage_path and self.storage_path.exists():
            self._load_state()

    def can_afford(self, estimated_amount: Decimal | str | float) -> bool:
        amount = self._amount(estimated_amount)
        return (
            not self.breached
            and self.confirmed_spend_usd + self.reserved_spend_usd + amount
            <= self.limit_usd
            and self.calls_completed + len(self.reservations) < self.max_calls
        )

    def reserve(self, estimated_amount: Decimal | str | float) -> str:
        """Persist an allowance before emitting a request."""
        amount = self._amount(estimated_amount)
        with self._thread_lock, self._exclusive_lock():
            self._refresh_locked()
            if not self.can_afford(amount):
                raise BudgetExceededError("Presupuesto o número de llamadas agotado.")
            reservation_id = f"res_{uuid.uuid4().hex}"
            self.reservations[reservation_id] = amount
            self.reserved_spend_usd += amount
            self._persist_state_locked()
            return reservation_id

    def confirm(
        self,
        reservation_id: str,
        actual_spend: Decimal | str | float,
        tokens_used: int = 0,
    ) -> None:
        """Settle a known provider charge without allowing a silent overrun.

        If the provider reports more than was reserved, the overrun is recorded
        durably and the ledger is permanently blocked. The remote charge has
        already happened; raising without recording it would be less safe.
        """
        spent = self._amount(actual_spend)
        if not isinstance(tokens_used, int) or tokens_used < 0:
            raise ValueError("tokens_used inválido.")

        with self._thread_lock, self._exclusive_lock():
            self._refresh_locked()
            if reservation_id not in self.reservations:
                raise KeyError("Reserva inexistente o ya finalizada.")

            reserved = self.reservations.pop(reservation_id)
            self.reserved_spend_usd -= reserved
            self.confirmed_spend_usd += spent
            self.calls_completed += 1
            self.tokens_consumed += tokens_used
            overrun = spent > reserved or self.confirmed_spend_usd > self.limit_usd
            self.breached = self.breached or overrun
            self._persist_state_locked()

            if overrun:
                raise BudgetExceededError(
                    "El coste real superó la reserva o el límite; ledger bloqueado."
                )

    def release_before_dispatch(self, reservation_id: str) -> None:
        """Release only when the caller can prove that no request was sent."""
        with self._thread_lock, self._exclusive_lock():
            self._refresh_locked()
            reserved = self.reservations.pop(reservation_id, None)
            if reserved is not None:
                self.reserved_spend_usd -= reserved
                self._persist_state_locked()

    def _state(self) -> BudgetState:
        return BudgetState(
            limit_usd=str(self.limit_usd),
            confirmed_spend_usd=str(self.confirmed_spend_usd),
            reserved_spend_usd=str(self.reserved_spend_usd),
            max_calls=self.max_calls,
            calls_completed=self.calls_completed,
            max_output_tokens=self.max_output_tokens,
            tokens_consumed=self.tokens_consumed,
            reservations={key: str(value) for key, value in self.reservations.items()},
            breached=self.breached,
        )

    def _persist_state_locked(self) -> None:
        if self.storage_path is None:
            return
        content = self._state().model_dump_json(indent=2)
        fd, temporary_name = tempfile.mkstemp(
            dir=self.storage_path.parent, prefix="ledger_", suffix=".tmp"
        )
        temporary_path = Path(temporary_name)
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                handle.write(content)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temporary_path, self.storage_path)
        except Exception:
            temporary_path.unlink(missing_ok=True)
            raise

    def _load_state(self) -> None:
        assert self.storage_path is not None
        state = BudgetState.model_validate_json(self.storage_path.read_bytes())
        if Decimal(state.limit_usd) != self.limit_usd or state.max_calls != self.max_calls:
            raise BudgetExceededError("El ledger existente no coincide con el protocolo autorizado.")
        self.confirmed_spend_usd = Decimal(state.confirmed_spend_usd)
        self.reserved_spend_usd = Decimal(state.reserved_spend_usd)
        self.calls_completed = state.calls_completed
        self.max_output_tokens = state.max_output_tokens
        self.tokens_consumed = state.tokens_consumed
        self.reservations = {key: Decimal(value) for key, value in state.reservations.items()}
        self.breached = state.breached
