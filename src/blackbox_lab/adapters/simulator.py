import json
import math
from typing import Any, Dict

from blackbox_lab.adapters.base import TargetAdapter
from blackbox_lab.core.contracts import InputObservation, OutputObservation, RawDocument


class DeterministicSimulatorAdapter(TargetAdapter):
    """Adaptador de caja negra local simulada para pruebas locales sin coste ni red.

    Evalúa una función benchmark no lineal: f(x, y) = (x - 2)^2 + (y + 3)^2.
    """

    def __init__(self, target_x: float = 2.0, target_y: float = -3.0):
        self.target_x = target_x
        self.target_y = target_y
        self.total_invocations = 0

    async def execute(self, observation: InputObservation) -> OutputObservation:
        self.total_invocations += 1
        payload = observation.payload

        x = float(payload.get("x", 0.0))
        y = float(payload.get("y", 0.0))

        # f(x, y) = distancia al objetivo
        loss = (x - self.target_x) ** 2 + (y - self.target_y) ** 2
        score = 1.0 / (1.0 + loss)

        response_dict: Dict[str, Any] = {
            "loss": float(loss),
            "score": float(score),
            "convergence": bool(loss < 1e-4),
        }

        raw_doc = RawDocument(
            canonical_json=json.dumps(response_dict, sort_keys=True, separators=(",", ":"))
        )

        return OutputObservation(
            input_id=observation.id,
            raw_document=raw_doc,
            status="success",
            cost=0.0,
            duration_ms=1,
        )
