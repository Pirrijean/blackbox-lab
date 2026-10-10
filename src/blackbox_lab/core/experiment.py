from pydantic import BaseModel
from typing import Dict, List, Any
from blackbox_lab.core.contracts import BudgetPolicy, SecurityPolicy

class Hypothesis(BaseModel):
    description: str
    expected_observable: str

class VariableDef(BaseModel):
    values: List[Any]

class ExperimentConfig(BaseModel):
    id: str
    version: str
    objective: str
    hypothesis: Hypothesis
    target_adapter: str
    model_id: str
    variables: Dict[str, VariableDef]
    replicates: int = 1
    budget: BudgetPolicy
    security: SecurityPolicy
