import json
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator


class BudgetPolicy(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, allow_inf_nan=False)

    max_cases: int = Field(..., gt=0, le=10_000)
    max_attempts_per_case: int = Field(default=1, ge=1, le=10)
    max_cost_usd: float = Field(default=0.0, ge=0.0, le=10_000.0)
    timeout_seconds: int = Field(default=60, gt=0, le=3600)


class SecurityPolicy(BaseModel):
    """Controles obligatorios no desactivables (Fase 6)."""
    model_config = ConfigDict(extra="forbid", frozen=True)

    authorization_required: Literal[True] = True
    data_redaction: Literal[True] = True
    stop_on_budget_limit: Literal[True] = True


class RawDocument(BaseModel):
    """Representación normalizada, canónica e inmutable de evidencia (Fase 7)."""
    model_config = ConfigDict(
        extra="forbid",
        frozen=True,
        strict=True,
    )

    canonical_json: str

    @field_validator("canonical_json")
    @classmethod
    def validate_json(cls, value: str) -> str:
        if len(value.encode("utf-8")) > 1_000_000:
            raise ValueError("Documento demasiado grande.")

        def reject_constant(_):
            raise ValueError("JSON con valor no finito.")

        def reject_duplicate_keys(pairs):
            result = {}
            for key, val in pairs:
                if key in result:
                    raise ValueError(f"JSON con claves duplicadas: '{key}'.")
                result[key] = val
            return result

        document = json.loads(
            value,
            parse_constant=reject_constant,
            object_pairs_hook=reject_duplicate_keys,
        )
        return json.dumps(
            document,
            ensure_ascii=False,
            allow_nan=False,
            sort_keys=True,
            separators=(",", ":"),
        )


class InputObservation(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, allow_inf_nan=False)

    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    raw_document: RawDocument
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    @property
    def payload(self) -> dict[str, Any]:
        document = json.loads(self.raw_document.canonical_json)
        if not isinstance(document, dict):
            raise ValueError("La entrada debe ser un objeto JSON.")
        return document


class OutputObservation(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, allow_inf_nan=False)

    input_id: str
    raw_document: Optional[RawDocument] = None
    status: Literal["success", "failure", "blocked", "timeout"] = "success"
    error_details: Optional[str] = None
    cost: float = Field(0.0, ge=0.0)
    duration_ms: int = Field(0, ge=0)
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    @property
    def response(self) -> dict[str, Any]:
        if self.raw_document is None:
            return {}
        document = json.loads(self.raw_document.canonical_json)
        if not isinstance(document, dict):
            raise ValueError("La respuesta debe ser un objeto JSON.")
        return document
