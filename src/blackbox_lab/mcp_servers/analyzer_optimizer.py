import json
import math
import os
from pathlib import Path

import numpy as np
import optuna
from mcp.server.fastmcp import FastMCP
from scipy.stats import t

mcp = FastMCP("restricted-analyzer")
CONFIG_PATH = os.environ.get("FRONTIER_CONFIG", "configs/demo.json")
optuna.logging.set_verbosity(optuna.logging.WARNING)


def load_config() -> dict:
    path = Path(CONFIG_PATH)
    if not path.is_file():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def numeric_summary(values: list[float]) -> dict:
    if not values or any(not math.isfinite(v) for v in values):
        raise ValueError("Valores numéricos no válidos.")

    data = np.asarray(values, dtype=float)
    mean = float(data.mean())

    if len(data) == 1:
        return {
            "n": 1,
            "mean": mean,
            "std": None,
            "ci95": None,
            "limitation": "No puede estimarse variabilidad con n=1.",
        }

    std = float(data.std(ddof=1))
    margin = float(t.ppf(0.975, len(data) - 1)) * std / math.sqrt(len(data))

    return {
        "n": len(data),
        "mean": mean,
        "std": std,
        "ci95": [mean - margin, mean + margin],
        "limitation": "Student-t para muestras independientes.",
    }


@mcp.tool()
def summarize(rows_json: str) -> str:
    rows = json.loads(rows_json)
    if not isinstance(rows, list):
        raise ValueError("Se esperaba una lista de resultados.")

    config = load_config()
    metric_key = config.get("metric_key", "value")

    groups = {}
    valid_count = 0
    failure_count = 0

    for row in rows:
        if row.get("status") != "completed":
            failure_count += 1
            continue

        valid_count += 1
        measurement = row.get("measurement")
        if measurement is None and "response" in row:
            measurement = row["response"].get(metric_key)

        if measurement is not None:
            key = json.dumps(row.get("payload", {}), sort_keys=True)
            groups.setdefault(key, []).append(float(measurement))

    metrics_by_input = {}
    for key, vals in groups.items():
        metrics_by_input[key] = numeric_summary(vals)

    report = {
        "total_cases": len(rows),
        "valid_cases": valid_count,
        "failed_cases": failure_count,
        "metrics_by_input": metrics_by_input,
        "conclusion": "Resumen experimental descriptivo sin intervención humana.",
    }
    return json.dumps(report, ensure_ascii=False)


@mcp.tool()
def suggest(history_json: str) -> str:
    history = json.loads(history_json)
    config = load_config()
    variables = config.get("variables", {})

    study = optuna.create_study(
        direction=config.get("direction", "minimize"),
        sampler=optuna.samplers.TPESampler(seed=int(config.get("seed", 42))),
    )

    for row in history:
        if row.get("status") == "completed" and row.get("measurement") is not None:
            study.add_trial(
                optuna.trial.create_trial(
                    params=row.get("payload", {}),
                    distributions={
                        name: optuna.distributions.CategoricalDistribution(vals)
                        for name, vals in variables.items()
                    },
                    value=float(row["measurement"]),
                )
            )

    trial = study.ask()
    payload = {
        name: trial.suggest_categorical(name, vals)
        for name, vals in variables.items()
    }
    return json.dumps({"payload": payload})


if __name__ == "__main__":
    mcp.run(transport="stdio")
