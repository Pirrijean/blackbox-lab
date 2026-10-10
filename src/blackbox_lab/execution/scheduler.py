"""Fail-closed experiment execution and non-duplicating recovery."""

from __future__ import annotations

import hashlib
import json
import uuid
from decimal import Decimal
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict

from blackbox_lab.adapters.base import TargetAdapter
from blackbox_lab.core.contracts import InputObservation, RawDocument
from blackbox_lab.core.experiment import ExperimentConfig
from blackbox_lab.core.metrics import MetricResult, calculate_metrics
from blackbox_lab.execution.budgets import BudgetExceededError, BudgetManager
from blackbox_lab.execution.checkpoints import (
    CaseCheckpoint,
    CaseState,
    CheckpointManager,
    ExecutionState,
    RunCheckpoint,
)
from blackbox_lab.execution.evidence import EvidenceIntegrityError, EvidenceStore


class ExperimentRunResult(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, allow_inf_nan=False)

    experiment_id: str
    run_id: str
    state: str
    total_cases_planned: int
    cases_completed: int
    total_cost_usd: float
    metric_results: dict[str, MetricResult]
    reason: str


class ExperimentScheduler:
    """Executes only protocol-authorised cases exactly once per persisted state."""

    def __init__(
        self,
        config: ExperimentConfig,
        adapter: TargetAdapter,
        budget_manager: BudgetManager | None = None,
        checkpoint_manager: CheckpointManager | None = None,
        evidence_store: EvidenceStore | None = None,
    ):
        # Reconstruct even a model_construct() instance before using it.
        self.config = ExperimentConfig.model_validate(config.model_dump(mode="json"))
        self.adapter = adapter
        self.checkpoint_manager = checkpoint_manager or CheckpointManager()
        self.budget_manager = budget_manager or BudgetManager(
            limit_usd=self.config.budget.max_cost_usd,
            max_calls=self.config.budget.max_cases,
            storage_path=Path("./data/ledger") / f"{self.config.id}.json",
        )
        if (
            self.budget_manager.limit_usd != self.config.budget.max_cost_usd
            or self.budget_manager.max_calls != self.config.budget.max_cases
        ):
            raise ValueError("El ledger no coincide con el presupuesto autorizado.")
        self.evidence_store = evidence_store or EvidenceStore()

    @property
    def protocol_hash(self) -> str:
        payload = json.dumps(
            self.config.model_dump(mode="json"),
            sort_keys=True,
            separators=(",", ":"),
        )
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()

    def _case_id(self, run_id: str, index: int) -> str:
        digest = hashlib.sha256(f"{run_id}:{index}".encode("utf-8")).hexdigest()[:32]
        return f"case_{digest}"

    def _new_checkpoint(self, run_id: str) -> RunCheckpoint:
        cases = []
        for index, payload in enumerate(self.config.iter_cases()):
            raw = RawDocument(canonical_json=json.dumps(payload, sort_keys=True, separators=(",", ":")))
            cases.append(
                CaseCheckpoint(
                    case_id=self._case_id(run_id, index),
                    payload_json=raw.canonical_json,
                )
            )
        return RunCheckpoint(
            experiment_id=self.config.id,
            run_id=run_id,
            protocol_hash=self.protocol_hash,
            state=ExecutionState.RUNNING,
            completed_cases=0,
            total_cases=len(cases),
            current_cost=0.0,
            cases=tuple(cases),
        )

    def _save(self, checkpoint: RunCheckpoint) -> RunCheckpoint:
        existing = self.checkpoint_manager.load_checkpoint(checkpoint.run_id)
        return self.checkpoint_manager.save_checkpoint(
            checkpoint,
            expected_revision=checkpoint.revision if existing is not None else None,
        )

    def _result(self, checkpoint: RunCheckpoint, state: ExecutionState, reason: str) -> ExperimentRunResult:
        metrics: dict[str, MetricResult] = {}
        try:
            scores = self._scores_for(checkpoint)
            if scores:
                metrics["primary_metric"] = calculate_metrics(scores)
        except (EvidenceIntegrityError, ValueError):
            state = ExecutionState.INDETERMINATE
            reason = "La evidencia no pasó su comprobación de integridad."

        return ExperimentRunResult(
            experiment_id=self.config.id,
            run_id=checkpoint.run_id,
            state=state.value,
            total_cases_planned=checkpoint.total_cases,
            cases_completed=checkpoint.completed_cases,
            total_cost_usd=float(self.budget_manager.confirmed_spend_usd),
            metric_results=metrics,
            reason=reason,
        )

    def _scores_for(self, checkpoint: RunCheckpoint) -> list[float]:
        wanted = {case.evidence_id for case in checkpoint.cases if case.evidence_id}
        if not wanted:
            return []
        values: list[float] = []
        for record in self.evidence_store.load_records(self.config.id):
            if record.record_id not in wanted:
                continue
            response = json.loads(record.raw_output_json)
            value = response.get("score", response.get("loss"))
            if isinstance(value, bool) or not isinstance(value, (int, float)):
                raise ValueError("La métrica de evidencia no es numérica.")
            values.append(float(value))
        if len(values) != len(wanted):
            raise EvidenceIntegrityError("Falta evidencia de un caso completado.")
        return values

    async def run(self, run_id: str) -> ExperimentRunResult:
        existing = self.checkpoint_manager.load_checkpoint(run_id)
        if existing is None:
            checkpoint = self._save(self._new_checkpoint(run_id))
        else:
            checkpoint = existing
            if checkpoint.experiment_id != self.config.id or checkpoint.protocol_hash != self.protocol_hash:
                raise ValueError("No se puede reanudar con un protocolo distinto.")
            if checkpoint.state == ExecutionState.COMPLETED:
                return self._result(checkpoint, ExecutionState.COMPLETED, "Experimento ya completado.")

        # An incomplete persisted reservation may have been dispatched before a
        # crash. Never replay it automatically.
        uncertain = [case for case in checkpoint.cases if case.state == CaseState.RESERVED]
        if uncertain or self.budget_manager.reservations:
            updated = tuple(
                case.model_copy(
                    update={"state": CaseState.INDETERMINATE, "detail": "Solicitud previa sin resultado verificable."}
                )
                if case.state == CaseState.RESERVED
                else case
                for case in checkpoint.cases
            )
            checkpoint = self._save(
                checkpoint.model_copy(
                    update={"state": ExecutionState.INDETERMINATE, "cases": updated}
                )
            )
            return self._result(
                checkpoint,
                ExecutionState.INDETERMINATE,
                "Hay solicitudes previas de estado incierto; no se duplican.",
            )

        for index, case in enumerate(checkpoint.cases):
            if case.state == CaseState.SUCCEEDED:
                continue
            if case.state != CaseState.PENDING:
                checkpoint = self._save(
                    checkpoint.model_copy(update={"state": ExecutionState.INDETERMINATE})
                )
                return self._result(checkpoint, ExecutionState.INDETERMINATE, "Caso no repetible.")

            if case.attempts >= self.config.budget.max_attempts_per_case:
                checkpoint = self._save(
                    checkpoint.model_copy(update={"state": ExecutionState.BLOCKED})
                )
                return self._result(checkpoint, ExecutionState.BLOCKED, "Máximo de intentos por caso agotado.")

            try:
                reservation_id = self.budget_manager.reserve(
                    self.config.budget.max_cost_per_attempt_usd
                )
            except BudgetExceededError:
                checkpoint = self._save(
                    checkpoint.model_copy(update={"state": ExecutionState.BLOCKED})
                )
                return self._result(checkpoint, ExecutionState.BLOCKED, "Presupuesto agotado antes de emitir una consulta.")

            request_id = f"req_{uuid.uuid4().hex}"
            input_id = str(uuid.uuid5(uuid.NAMESPACE_URL, f"{run_id}:{case.case_id}"))
            reserved_case = case.model_copy(
                update={
                    "state": CaseState.RESERVED,
                    "attempts": case.attempts + 1,
                    "request_id": request_id,
                    "reservation_id": reservation_id,
                    "input_id": input_id,
                }
            )
            cases = list(checkpoint.cases)
            cases[index] = reserved_case
            checkpoint = self._save(checkpoint.model_copy(update={"cases": tuple(cases)}))

            observation = InputObservation(
                id=input_id, raw_document=RawDocument(canonical_json=case.payload_json)
            )
            try:
                output = await self.adapter.execute(observation, request_id=request_id)
            except Exception:
                checkpoint = self._save(
                    checkpoint.model_copy(
                        update={
                            "state": ExecutionState.INDETERMINATE,
                            "cases": tuple(
                                item.model_copy(
                                    update={"state": CaseState.INDETERMINATE, "detail": "Error tras despacho."}
                                )
                                if item.case_id == case.case_id
                                else item
                                for item in checkpoint.cases
                            ),
                        }
                    )
                )
                return self._result(checkpoint, ExecutionState.INDETERMINATE, "La consulta pudo haberse ejecutado; no se reintenta.")

            if output.status != "success" or output.cost is None:
                checkpoint = self._save(
                    checkpoint.model_copy(
                        update={
                            "state": ExecutionState.INDETERMINATE,
                            "cases": tuple(
                                item.model_copy(
                                    update={"state": CaseState.INDETERMINATE, "detail": "Respuesta sin coste o éxito verificable."}
                                )
                                if item.case_id == case.case_id
                                else item
                                for item in checkpoint.cases
                            ),
                        }
                    )
                )
                return self._result(checkpoint, ExecutionState.INDETERMINATE, "Resultado remoto no liquidable; reserva retenida.")

            try:
                self.evidence_store.append_record(
                    self.config.id, observation, output, record_id=case.case_id
                )
                self.budget_manager.confirm(reservation_id, Decimal(str(output.cost)))
            except (BudgetExceededError, EvidenceIntegrityError, OSError, ValueError):
                checkpoint = self._save(
                    checkpoint.model_copy(
                        update={
                            "state": ExecutionState.INDETERMINATE,
                            "cases": tuple(
                                item.model_copy(
                                    update={"state": CaseState.INDETERMINATE, "detail": "Evidencia o liquidación no verificable."}
                                )
                                if item.case_id == case.case_id
                                else item
                                for item in checkpoint.cases
                            ),
                        }
                    )
                )
                return self._result(checkpoint, ExecutionState.INDETERMINATE, "Se detuvo tras una respuesta remota no conciliada.")

            cases = list(checkpoint.cases)
            cases[index] = reserved_case.model_copy(
                update={"state": CaseState.SUCCEEDED, "evidence_id": case.case_id}
            )
            completed = sum(item.state == CaseState.SUCCEEDED for item in cases)
            checkpoint = self._save(
                checkpoint.model_copy(
                    update={
                        "cases": tuple(cases),
                        "completed_cases": completed,
                        "current_cost": float(self.budget_manager.confirmed_spend_usd),
                    }
                )
            )

        checkpoint = self._save(
            checkpoint.model_copy(update={"state": ExecutionState.COMPLETED})
        )
        return self._result(checkpoint, ExecutionState.COMPLETED, "Experimento completado con evidencia verificada.")

    async def resume(self, run_id: str) -> ExperimentRunResult:
        return await self.run(run_id)
