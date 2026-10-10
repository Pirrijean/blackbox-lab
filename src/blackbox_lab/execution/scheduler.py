import asyncio
import json
import logging
from decimal import Decimal
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, ConfigDict

from blackbox_lab.adapters.base import TargetAdapter
from blackbox_lab.core.contracts import InputObservation, OutputObservation, RawDocument
from blackbox_lab.core.experiment import ExperimentConfig
from blackbox_lab.core.metrics import MetricResult, calculate_metrics
from blackbox_lab.execution.budgets import BudgetExceededError, BudgetManager
from blackbox_lab.execution.checkpoints import CheckpointManager, ExecutionState, RunCheckpoint
from blackbox_lab.execution.evidence import EvidenceStore

logger = logging.getLogger(__name__)


class ExperimentRunResult(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    experiment_id: str
    run_id: str
    state: str
    total_cases_planned: int
    cases_completed: int
    total_cost_usd: float
    metric_results: Dict[str, MetricResult]
    reason: str


class ExperimentScheduler:
    """Orquestador de experimentos de caja negra con presupuesto y evidencia protegida."""

    def __init__(
        self,
        config: ExperimentConfig,
        adapter: TargetAdapter,
        budget_manager: Optional[BudgetManager] = None,
        checkpoint_manager: Optional[CheckpointManager] = None,
        evidence_store: Optional[EvidenceStore] = None,
    ):
        self.config = config
        self.adapter = adapter
        self.budget_manager = budget_manager or BudgetManager(
            limit_usd=config.budget.max_cost_usd or Decimal("5.00"),
            max_calls=config.budget.max_cases * config.replicates,
        )
        self.checkpoint_manager = checkpoint_manager or CheckpointManager()
        self.evidence_store = evidence_store or EvidenceStore()

    async def run(self, run_id: str) -> ExperimentRunResult:
        # Generar casos a partir de las variables
        cases = self._generate_cases()
        total_cases = len(cases)

        checkpoint = RunCheckpoint(
            experiment_id=self.config.id,
            run_id=run_id,
            state=ExecutionState.RUNNING,
            completed_cases=0,
            total_cases=total_cases,
            current_cost=0.0,
        )
        self.checkpoint_manager.save_checkpoint(checkpoint)

        collected_scores: List[float] = []
        completed = 0
        total_spent = Decimal("0.00")
        failure_reason = "Experimento completado exitosamente."

        for case_idx, case_payload in enumerate(cases):
            # 1. Comprobar y reservar presupuesto (estimación: $0.001 por llamada o 0 si local)
            cost_estimate = Decimal("0.001")
            try:
                res_id = self.budget_manager.reserve(cost_estimate)
            except BudgetExceededError as exc:
                failure_reason = f"Detenido por límite presupuestario: {exc}"
                logger.warning(failure_reason)
                break

            # 2. Ejecutar a través del adaptador aislado
            raw_input_doc = RawDocument(
                canonical_json=json.dumps(case_payload, sort_keys=True, separators=(",", ":"))
            )
            input_obs = InputObservation(raw_document=raw_input_doc)

            try:
                output_obs = await self.adapter.execute(input_obs)
                actual_cost = Decimal(str(output_obs.cost if output_obs.cost is not None else 0.0))
                self.budget_manager.confirm(res_id, actual_cost)
                total_spent += actual_cost

                # 3. Guardar evidencia inmutable
                self.evidence_store.append_record(self.config.id, input_obs, output_obs)

                # Extraer valor numérico si existe para análisis
                if output_obs.response:
                    if "score" in output_obs.response:
                        collected_scores.append(float(output_obs.response["score"]))
                    elif "loss" in output_obs.response:
                        collected_scores.append(float(output_obs.response["loss"]))

                completed += 1

                # Actualizar checkpoint
                checkpoint = RunCheckpoint(
                    experiment_id=self.config.id,
                    run_id=run_id,
                    state=ExecutionState.RUNNING,
                    completed_cases=completed,
                    total_cases=total_cases,
                    current_cost=float(total_spent),
                )
                self.checkpoint_manager.save_checkpoint(checkpoint)

            except Exception as exc:
                self.budget_manager.release(res_id)
                failure_reason = f"Fallo en caso {case_idx}: {exc}"
                logger.error(failure_reason)
                break

        # 4. Calcular métricas estadísticas rigurosas
        metrics_dict: Dict[str, MetricResult] = {}
        if collected_scores:
            metrics_dict["primary_metric"] = calculate_metrics(collected_scores)

        final_state = ExecutionState.COMPLETED if completed == total_cases else ExecutionState.FAILED

        checkpoint = RunCheckpoint(
            experiment_id=self.config.id,
            run_id=run_id,
            state=final_state,
            completed_cases=completed,
            total_cases=total_cases,
            current_cost=float(total_spent),
        )
        self.checkpoint_manager.save_checkpoint(checkpoint)

        return ExperimentRunResult(
            experiment_id=self.config.id,
            run_id=run_id,
            state=final_state.value,
            total_cases_planned=total_cases,
            cases_completed=completed,
            total_cost_usd=float(total_spent),
            metric_results=metrics_dict,
            reason=failure_reason,
        )

    def _generate_cases(self) -> List[Dict[str, Any]]:
        # Generación sencilla de combinaciones o casos
        cases = []
        for var_name, var_def in self.config.variables.items():
            for val in var_def.values:
                for rep in range(self.config.replicates):
                    cases.append({var_name: val, "replicate": rep})
        return cases if cases else [{"dummy": 0}]
