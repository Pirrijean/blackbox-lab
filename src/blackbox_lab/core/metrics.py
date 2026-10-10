import math
from typing import Literal

import numpy as np
from pydantic import BaseModel, ConfigDict
from scipy.stats import t


class MetricResult(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
        frozen=True,
        allow_inf_nan=False,
    )

    n: int
    mean: float
    std_dev: float | None
    confidence_interval_95: tuple[float, float] | None
    method: Literal["student_t"]
    limitation: str | None = None


def calculate_metrics(values: list[float]) -> MetricResult:
    if not values:
        raise ValueError("No hay observaciones para calcular métricas.")

    if any(
        isinstance(value, bool)
        or not isinstance(value, (int, float))
        or not math.isfinite(value)
        for value in values
    ):
        raise ValueError("Se requieren valores numéricos finitos.")

    data = np.asarray(values, dtype=float)
    n = len(data)
    mean = float(data.mean())

    if not math.isfinite(mean):
        raise ValueError("Desbordamiento numérico al calcular la media.")

    if n == 1:
        return MetricResult(
            n=1,
            mean=mean,
            std_dev=None,
            confidence_interval_95=None,
            method="student_t",
            limitation="Una observación no permite estimar la variabilidad.",
        )

    std_dev = float(data.std(ddof=1))
    margin = float(t.ppf(0.975, df=n - 1)) * std_dev / math.sqrt(n)
    lower, upper = mean - margin, mean + margin

    if not all(math.isfinite(v) for v in (std_dev, lower, upper)):
        raise ValueError("Desbordamiento numérico en la incertidumbre.")

    return MetricResult(
        n=n,
        mean=mean,
        std_dev=std_dev,
        confidence_interval_95=(lower, upper),
        method="student_t",
        limitation=(
            "Requiere observaciones independientes y supuestos apropiados "
            "para inferencia sobre la media. No corrige multiplicidad."
        ),
    )
