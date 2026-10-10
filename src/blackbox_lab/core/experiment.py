from typing import Any, Dict, List
from pydantic import BaseModel, ConfigDict, Field
from blackbox_lab.core.contracts import BudgetPolicy, SecurityPolicy
from blackbox_lab.execution.checkpoints import SAFE_ID_PATTERN


class Hypothesis(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    description: str = Field(..., min_length=1, max_length=1000)
    expected_observable: str = Field(..., min_length=1, max_length=1000)


class VariableDef(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    values: List[Any] = Field(..., min_length=1)


class ExperimentConfig(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    id: str = Field(..., pattern=SAFE_ID_PATTERN)
    version: str = Field("1.0", pattern=r"^\d+(\.\d+){0,2}$")
    objective: str = Field(..., min_length=1, max_length=2000)
    hypothesis: Hypothesis
    target_adapter: str = Field(..., pattern=r"^[A-Za-z0-9_-]{1,64}$")
    model_id: str = Field(..., pattern=r"^[A-Za-z0-9_.-]{1,64}$")
    variables: Dict[str, VariableDef]
    replicates: int = Field(1, ge=1, le=100)
    budget: BudgetPolicy
    security: SecurityPolicy
