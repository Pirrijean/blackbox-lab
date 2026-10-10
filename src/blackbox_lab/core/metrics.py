from pydantic import BaseModel
import numpy as np

class MetricResult(BaseModel):
    mean: float
    std_dev: float
    confidence_interval_95: tuple[float, float]
    
def calculate_metrics(values: list[float]) -> MetricResult:
    """Calcula la incertidumbre y métricas en lugar de asumir respuestas exactas."""
    if not values:
        return MetricResult(mean=0.0, std_dev=0.0, confidence_interval_95=(0.0, 0.0))
        
    mean = np.mean(values)
    std_dev = np.std(values, ddof=1) if len(values) > 1 else 0.0
    
    # 95% CI roughly mean +/- 1.96 * (std / sqrt(n))
    margin = 1.96 * (std_dev / np.sqrt(len(values))) if len(values) > 1 else 0.0
    
    return MetricResult(
        mean=float(mean),
        std_dev=float(std_dev),
        confidence_interval_95=(float(mean - margin), float(mean + margin))
    )
