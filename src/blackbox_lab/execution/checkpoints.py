"""Versioned checkpoint state for non-duplicating experiment recovery."""

from __future__ import annotations

import os
import re
import tempfile
from enum import Enum
from pathlib import Path
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field, model_validator

SAFE_ID_PATTERN = r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,63}$"


class ExecutionState(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    BLOCKED = "blocked"
    INDETERMINATE = "indeterminate"
    INTERRUPTED = "interrupted"


class CaseState(str, Enum):
    PENDING = "pending"
    RESERVED = "reserved"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    INDETERMINATE = "indeterminate"


class CaseCheckpoint(BaseModel):
    """The durable state of one outbound operation.

    RESERVED means dispatch may have happened.  It is never automatically
    changed back to PENDING on resume.
    """

    model_config = ConfigDict(extra="forbid", frozen=True, allow_inf_nan=False)

    case_id: str = Field(..., pattern=SAFE_ID_PATTERN)
    payload_json: str = Field(..., min_length=2, max_length=1_000_000)
    state: CaseState = CaseState.PENDING
    attempts: int = Field(0, ge=0, le=10, strict=True)
    request_id: str | None = Field(None, pattern=SAFE_ID_PATTERN)
    reservation_id: str | None = Field(None, pattern=r"^res_[a-f0-9]{32}$")
    input_id: str | None = Field(None, pattern=SAFE_ID_PATTERN)
    evidence_id: str | None = Field(None, pattern=SAFE_ID_PATTERN)
    detail: str | None = Field(None, max_length=500)

    @model_validator(mode="after")
    def validate_state(self):
        if self.state == CaseState.PENDING:
            if any((self.request_id, self.reservation_id, self.input_id, self.evidence_id)):
                raise ValueError("Un caso pendiente no puede tener efectos persistidos.")
        elif not all((self.request_id, self.reservation_id, self.input_id)):
            raise ValueError("Un caso emitido debe conservar solicitud, reserva e input.")
        if self.state == CaseState.SUCCEEDED and self.evidence_id is None:
            raise ValueError("Un caso correcto debe tener evidencia persistida.")
        return self


class RunCheckpoint(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
        frozen=True,
        allow_inf_nan=False,
        revalidate_instances="always",
    )

    experiment_id: str = Field(..., pattern=SAFE_ID_PATTERN)
    run_id: str = Field(..., pattern=SAFE_ID_PATTERN)
    protocol_hash: str = Field("", max_length=64)
    revision: int = Field(0, ge=0, strict=True)
    state: ExecutionState
    completed_cases: int = Field(0, ge=0, strict=True)
    total_cases: int = Field(..., ge=1, le=10_000, strict=True)
    current_cost: float = Field(0.0, ge=0.0, le=10_000.0, strict=True)
    cases: tuple[CaseCheckpoint, ...] = ()

    @model_validator(mode="after")
    def validate_cases(self) -> "RunCheckpoint":
        if self.completed_cases > self.total_cases:
            raise ValueError("completed_cases supera total_cases.")
        if self.cases:
            if len(self.cases) != self.total_cases:
                raise ValueError("El checkpoint debe conservar el estado de todos los casos.")
            completed = sum(case.state == CaseState.SUCCEEDED for case in self.cases)
            if completed != self.completed_cases:
                raise ValueError("completed_cases no coincide con el estado por caso.")
        if self.state == ExecutionState.COMPLETED and self.completed_cases != self.total_cases:
            raise ValueError("Un checkpoint completado debe cubrir todos los casos.")
        return self


class CheckpointConflictError(RuntimeError):
    """Another writer changed the run state before this writer committed."""


class CheckpointManager:
    def __init__(self, storage_dir: str = "./data/checkpoints"):
        self.storage_dir = Path(storage_dir).resolve()
        self.storage_dir.mkdir(parents=True, exist_ok=True)

    def _resolve_safe_path(self, run_id: str) -> Path:
        if not isinstance(run_id, str) or not re.fullmatch(SAFE_ID_PATTERN, run_id):
            raise ValueError("Identificador de ejecución inseguro o inválido.")
        target_path = (self.storage_dir / f"{run_id}.json").resolve()
        try:
            target_path.relative_to(self.storage_dir)
        except ValueError as exc:
            raise ValueError("Acceso fuera del directorio autorizado de checkpoints.") from exc
        if target_path.exists() and target_path.is_symlink():
            raise ValueError("El checkpoint no puede ser un enlace simbólico.")
        return target_path

    def save_checkpoint(
        self, checkpoint: RunCheckpoint, *, expected_revision: int | None = None
    ) -> RunCheckpoint:
        """Atomically persist a new revision, refusing lost updates."""
        target_path = self._resolve_safe_path(checkpoint.run_id)
        existing = self.load_checkpoint(checkpoint.run_id)
        if expected_revision is not None:
            actual = -1 if existing is None else existing.revision
            if actual != expected_revision:
                raise CheckpointConflictError("El checkpoint cambió en otro escritor.")
        elif existing is not None and existing.revision > checkpoint.revision:
            raise CheckpointConflictError("No se permite sobrescribir una revisión más nueva.")

        persisted = checkpoint.model_copy(
            update={"revision": (existing.revision + 1) if existing else 0}
        )
        content = persisted.model_dump_json(indent=2)
        fd, temporary_name = tempfile.mkstemp(dir=self.storage_dir, prefix="checkpoint_", suffix=".tmp")
        temporary_path = Path(temporary_name)
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                handle.write(content)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temporary_path, target_path)
        except Exception:
            temporary_path.unlink(missing_ok=True)
            raise
        return persisted

    def load_checkpoint(self, run_id: str) -> Optional[RunCheckpoint]:
        target_path = self._resolve_safe_path(run_id)
        if not target_path.exists():
            return None
        with target_path.open("rb") as handle:
            content = handle.read(256 * 1024 + 1)
        if len(content) > 256 * 1024:
            raise ValueError("Checkpoint demasiado grande.")
        checkpoint = RunCheckpoint.model_validate_json(content)
        if checkpoint.run_id != run_id:
            raise ValueError("La identidad del checkpoint no coincide.")
        return checkpoint
