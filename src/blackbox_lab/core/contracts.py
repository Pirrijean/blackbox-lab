import json
import uuid
from datetime import datetime, timezone
from decimal import Decimal
from typing import Literal

from pydantic import (
    AwareDatetime,
    BaseModel,
    ConfigDict,
    Field,
    field_validator,
    model_validator,
)

SAFE_ID_PATTERN = r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,63}$"
MAX_DOCUMENT_BYTES = 1_000_000


class StrictContract(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
        frozen=True,
        strict=True,
        allow_inf_nan=False,
        revalidate_instances="always",
    )


class BudgetPolicy(StrictContract):
    max_cases: int = Field(..., gt=0, le=10_000, strict=True)
    max_attempts_per_case: int = Field(1, ge=1, le=10, strict=True)
    # A zero-cost protocol is allowed only for adapters that reserve and report
    # zero.  It must never be interpreted as an unspecified five-dollar limit.
    max_cost_usd: Decimal = Field(Decimal("0"), ge=0, le=10_000)
    max_cost_per_attempt_usd: Decimal = Field(Decimal("0"), ge=0, le=10_000)
    timeout_seconds: int = Field(60, gt=0, le=3600, strict=True)

    @field_validator("max_cost_usd", "max_cost_per_attempt_usd", mode="before")
    @classmethod
    def decimal_cost(cls, value):
        try:
            amount = Decimal(str(value))
        except Exception as exc:
            raise ValueError("Coste inválido.") from exc
        if not amount.is_finite():
            raise ValueError("El coste debe ser finito.")
        return amount

    @model_validator(mode="after")
    def validate_cost_bounds(self):
        if self.max_cost_per_attempt_usd > self.max_cost_usd:
            raise ValueError(
                "El coste máximo por intento no puede superar el presupuesto total."
            )
        return self


class SecurityPolicy(StrictContract):
    authorization_required: Literal[True] = True
    data_redaction: Literal[True] = True
    stop_on_budget_limit: Literal[True] = True

    @field_validator(
        "authorization_required",
        "data_redaction",
        "stop_on_budget_limit",
        mode="before",
    )
    @classmethod
    def require_actual_true(cls, value):
        if type(value) is not bool or value is not True:
            raise ValueError("El control no puede deshabilitarse.")
        return value


def reject_constant(_value):
    raise ValueError("JSON con valor no finito.")


def unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("JSON con claves duplicadas.")
        result[key] = value
    return result


class RawDocument(StrictContract):
    """Snapshot JSON normalizado; no representa bytes HTTP originales."""

    canonical_json: str

    @field_validator("canonical_json")
    @classmethod
    def validate_document(cls, value):
        try:
            if len(value.encode("utf-8")) > MAX_DOCUMENT_BYTES:
                raise ValueError("Documento demasiado grande.")

            document = json.loads(
                value,
                parse_constant=reject_constant,
                object_pairs_hook=unique_object,
            )

            if not isinstance(document, dict):
                raise ValueError("Se requiere un objeto JSON.")

            stack = [(document, 0)]
            nodes = 0

            while stack:
                item, depth = stack.pop()
                nodes += 1

                if depth > 32 or nodes > 50_000:
                    raise ValueError("Documento demasiado complejo.")

                if isinstance(item, dict):
                    stack.extend(
                        (child, depth + 1) for child in item.values()
                    )
                elif isinstance(item, list):
                    stack.extend((child, depth + 1) for child in item)

            canonical = json.dumps(
                document,
                ensure_ascii=False,
                allow_nan=False,
                sort_keys=True,
                separators=(",", ":"),
            )

            if len(canonical.encode("utf-8")) > MAX_DOCUMENT_BYTES:
                raise ValueError("Documento normalizado demasiado grande.")

            return canonical

        except (UnicodeError, RecursionError) as exc:
            raise ValueError("Documento JSON inválido o demasiado complejo.") from exc


class InputObservation(StrictContract):
    id: str = Field(
        default_factory=lambda: str(uuid.uuid4()),
        pattern=SAFE_ID_PATTERN,
    )
    raw_document: RawDocument
    timestamp: AwareDatetime = Field(
        default_factory=lambda: datetime.now(timezone.utc)
    )

    @property
    def payload(self):
        # Cada acceso devuelve una copia independiente.
        return json.loads(self.raw_document.canonical_json)


class OutputObservation(StrictContract):
    input_id: str = Field(..., pattern=SAFE_ID_PATTERN)
    raw_document: RawDocument | None = None
    status: Literal[
        "success", "failure", "blocked", "timeout", "indeterminate"
    ]
    error_code: Literal[
        "transport",
        "invalid_output",
        "policy",
        "deadline",
        "unknown_result",
    ] | None = None

    # None significa coste desconocido, no gratuito.
    cost: float | None = Field(None, ge=0)
    duration_ms: int = Field(0, ge=0)
    timestamp: AwareDatetime = Field(
        default_factory=lambda: datetime.now(timezone.utc)
    )

    @model_validator(mode="after")
    def consistent_output(self):
        if self.status == "success":
            if self.raw_document is None or self.error_code is not None:
                raise ValueError("Éxito requiere evidencia y ausencia de error.")
        elif self.error_code is None:
            raise ValueError("Un resultado no exitoso requiere error_code.")

        return self

    @property
    def response(self):
        if self.raw_document is None:
            return None
        return json.loads(self.raw_document.canonical_json)
