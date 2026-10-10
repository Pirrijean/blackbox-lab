from pydantic import BaseModel, Field, ConfigDict
from typing import Any, Dict, Optional
from datetime import datetime, timezone
import uuid

class BudgetPolicy(BaseModel):
    max_cases: int = Field(..., gt=0)
    max_attempts_per_case: int = Field(default=1, ge=1)
    max_cost_usd: float = Field(default=0.0, ge=0.0)
    timeout_seconds: int = Field(default=60, gt=0)

class SecurityPolicy(BaseModel):
    authorization_required: bool = True
    data_redaction: bool = True
    stop_on_budget_limit: bool = True

class InputObservation(BaseModel):
    model_config = ConfigDict(frozen=True)
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    payload: Dict[str, Any]
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

class OutputObservation(BaseModel):
    model_config = ConfigDict(frozen=True)
    input_id: str
    response: Dict[str, Any]
    status: str
    error_details: Optional[str] = None
    cost: float = 0.0
    duration_ms: int = 0
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
