import argparse
import asyncio
import sys

from blackbox_lab.adapters.simulator import DeterministicSimulatorAdapter
from blackbox_lab.core.contracts import BudgetPolicy, SecurityPolicy
from blackbox_lab.core.experiment import ExperimentConfig, Hypothesis, VariableDef
from blackbox_lab.core.metrics import calculate_metrics
from blackbox_lab.doctor import run_doctor
from blackbox_lab.execution.scheduler import ExperimentScheduler


def parse_args():
    parser = argparse.ArgumentParser(
        description="CLI de desarrollo y ejecución experimental para blackbox-lab.",
        prog="python -m blackbox_lab.cli",
    )
    subparsers = parser.add_subparsers(dest="command", help="Comando a ejecutar")

    # doctor
    subparsers.add_parser("doctor", help="Comprueba el entorno local y dependencias")

    # run-simulation
    subparsers.add_parser("run-simulation", help="Ejecuta un experimento local determinista con evidencia y métricas")

    # inspect-metrics
    metrics_parser = subparsers.add_parser("inspect-metrics", help="Calcula métricas estadísticas con distribución t de Student")
    metrics_parser.add_argument("values", nargs="+", type=float, help="Valores numéricos de muestra")

    return parser.parse_args()


async def execute_simulation():
    print("[*] Configurando experimento de prueba local determinista...")
    config = ExperimentConfig(
        id="sim_exp_01",
        version="1.0",
        objective="Optimizar parámetros x, y contra simulador determinista",
        hypothesis=Hypothesis(
            description="La convergencia se alcanza en el punto (2, -3)",
            expected_observable="Puntuación score converge hacia 1.0",
        ),
        target_adapter="simulator",
        model_id="deterministic_benchmark",
        variables={
            "x": VariableDef(values=[1.0, 1.5, 2.0]),
            "y": VariableDef(values=[-2.5, -3.0]),
        },
        replicates=2,
        budget=BudgetPolicy(max_cases=10, max_cost_usd=1.0, timeout_seconds=30),
        security=SecurityPolicy(),
    )

    adapter = DeterministicSimulatorAdapter(target_x=2.0, target_y=-3.0)
    scheduler = ExperimentScheduler(config=config, adapter=adapter)

    print("[*] Ejecutando orquestador experimental...")
    result = await scheduler.run(run_id="run_sim_local")

    print("--------------------------------------------------")
    print(f"Estado final: {result.state}")
    print(f"Casos completados: {result.cases_completed} / {result.total_cases_planned}")
    print(f"Coste total: ${result.total_cost_usd:.4f}")
    if "primary_metric" in result.metric_results:
        m = result.metric_results["primary_metric"]
        print(f"Media estimada: {m.mean:.4f}")
        print(f"Desviación estándar: {m.std_dev:.4f}" if m.std_dev is not None else "Std: N/A")
        print(f"Intervalo de Confianza (95% Student-t): {m.confidence_interval_95}")
    print(f"Razón: {result.reason}")
    print("--------------------------------------------------")
    return 0


def main():
    args = parse_args()
    if args.command == "doctor":
        success = run_doctor()
        sys.exit(0 if success else 1)
    elif args.command == "run-simulation":
        exit_code = asyncio.run(execute_simulation())
        sys.exit(exit_code)
    elif args.command == "inspect-metrics":
        try:
            res = calculate_metrics(args.values)
            print(f"N: {res.n}")
            print(f"Media: {res.mean:.4f}")
            print(f"Desviación estándar: {res.std_dev}")
            print(f"IC 95%: {res.confidence_interval_95}")
            print(f"Método: {res.method}")
            sys.exit(0)
        except Exception as exc:
            print(f"Error al calcular métricas: {exc}")
            sys.exit(1)
    else:
        print("Uso: python -m blackbox_lab.cli [doctor | run-simulation | inspect-metrics] --help")
        sys.exit(0)


if __name__ == "__main__":
    main()
