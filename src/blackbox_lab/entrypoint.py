"""Punto de entrada desacoplado para evaluación oficial (Fase Entrypoint).

Este módulo actúa como adaptador del contrato oficial del juez de la hackathon.
Cuando se publique el brief a las 10:10 con el formato de entrada/salida requerido,
este archivo traduce los parámetros al ExperimentScheduler sin tocar la lógica interna.
"""

import asyncio
import sys
from typing import Any, Dict

from blackbox_lab.adapters.simulator import DeterministicSimulatorAdapter
from blackbox_lab.core.contracts import BudgetPolicy, SecurityPolicy
from blackbox_lab.core.experiment import ExperimentConfig, Hypothesis, VariableDef
from blackbox_lab.execution.scheduler import ExperimentScheduler


async def evaluate_experiment(payload: Dict[str, Any]) -> Dict[str, Any]:
    exp_id = payload.get("experiment_id", "eval_exp_01")
    config = ExperimentConfig(
        id=exp_id,
        version="1.0",
        objective=payload.get("objective", "Evaluación oficial"),
        hypothesis=Hypothesis(
            description="Hipótesis de evaluación del evaluador",
            expected_observable="Métricas medibles",
        ),
        target_adapter=payload.get("target_adapter", "simulator"),
        model_id=payload.get("model_id", "default_model"),
        variables=payload.get("variables", {"x": VariableDef(values=[1.0, 2.0])}),
        replicates=payload.get("replicates", 1),
        budget=BudgetPolicy(
            max_cases=payload.get("max_cases", 5),
            max_cost_usd=payload.get("max_cost_usd", 1.0),
        ),
        security=SecurityPolicy(),
    )

    adapter = DeterministicSimulatorAdapter()
    scheduler = ExperimentScheduler(config=config, adapter=adapter)
    result = await scheduler.run(run_id=payload.get("run_id", "eval_run_01"))

    return {
        "experiment_id": result.experiment_id,
        "run_id": result.run_id,
        "status": result.state,
        "cases_completed": result.cases_completed,
        "total_cases": result.total_cases_planned,
        "cost_usd": result.total_cost_usd,
        "reason": result.reason,
    }


def main():
    if len(sys.argv) > 1 and sys.argv[1] == "--health":
        print("OK: blackbox-lab entrypoint ready")
        sys.exit(0)

    sample_payload = {
        "experiment_id": "eval_test",
        "objective": "Verificar ejecución del evaluador",
    }
    res = asyncio.run(evaluate_experiment(sample_payload))
    print(res)


if __name__ == "__main__":
    main()
