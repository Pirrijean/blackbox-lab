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
    model_config = ConfigDict(extra="forbid", frozen=True)

    authorization_required: bool = True
    data_redaction: bool = True
    stop_on_budget_limit: bool = True


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

        document = json.loads(value, parse_constant=reject_constant)
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
    raw_document: Optional[RawDocument] = None
    payload: Dict[str, Any] = Field(default_factory=dict)
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class OutputObservation(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, allow_inf_nan=False)

    input_id: str
    raw_document: Optional[RawDocument] = None
    response: Dict[str, Any] = Field(default_factory=dict)
    status: Literal["success", "failure", "blocked", "timeout"] = "success"
    error_details: Optional[str] = None
    cost: float = Field(0.0, ge=0.0)
    duration_ms: int = Field(0, ge=0)
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
