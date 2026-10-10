from itertools import product
from types import MappingProxyType
from typing import Mapping, TypeAlias

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    field_serializer,
    field_validator,
    model_validator,
)
from blackbox_lab.core.contracts import BudgetPolicy, SecurityPolicy
from blackbox_lab.execution.checkpoints import SAFE_ID_PATTERN


class Hypothesis(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    description: str = Field(..., min_length=1, max_length=1000)
    expected_observable: str = Field(..., min_length=1, max_length=1000)


ScalarValue: TypeAlias = str | int | float | bool | None


class VariableDef(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    # Protocol inputs are strictly scalars. Nested mutable objects are deliberately rejected:
    # an experiment must not be mutated after it is authorised.
    values: tuple[ScalarValue, ...] = Field(..., min_length=1)

    @field_validator("values", mode="before")
    @classmethod
    def reject_mutable_or_nested(cls, values):
        if not isinstance(values, (list, tuple)):
            raise ValueError("Las variables deben ser una secuencia.")
        for v in values:
            if isinstance(v, (list, dict, set)):
                raise ValueError("No se admiten colecciones anidadas mutables en las variables.")
            if not isinstance(v, (str, int, float, bool, type(None))):
                raise ValueError(f"Tipo de valor no soportado en variables: {type(v)}")
        return tuple(values)

    @field_validator("values")
    @classmethod
    def finite_values(cls, values: tuple[ScalarValue, ...]):
        for value in values:
            if isinstance(value, float) and not value.is_integer() and not (-1e308 < value < 1e308):
                raise ValueError("Las variables no pueden contener valores no finitos.")
        return values


class ExperimentConfig(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    id: str = Field(..., pattern=SAFE_ID_PATTERN)
    version: str = Field("1.0", pattern=r"^\d+(\.\d+){0,2}$")
    objective: str = Field(..., min_length=1, max_length=2000)
    hypothesis: Hypothesis
    target_adapter: str = Field(..., pattern=r"^[A-Za-z0-9_-]{1,64}$")
    model_id: str = Field(..., pattern=r"^[A-Za-z0-9_.-]{1,64}$")
    variables: Mapping[str, VariableDef]
    replicates: int = Field(1, ge=1, le=100, strict=True)
    budget: BudgetPolicy
    security: SecurityPolicy

    @field_validator("variables")
    @classmethod
    def freeze_variables(cls, variables: Mapping[str, VariableDef]):
        if not variables:
            raise ValueError("El experimento necesita al menos una variable.")
        for name in variables:
            if not isinstance(name, str) or not name or len(name) > 64:
                raise ValueError("Nombre de variable inválido.")
        return MappingProxyType(dict(variables))

    @field_serializer("variables")
    def serialize_variables(self, variables: Mapping[str, VariableDef]):
        return dict(variables)

    @model_validator(mode="after")
    def validate_case_budget(self):
        combinations = 1
        for variable in self.variables.values():
            combinations *= len(variable.values)
        total_cases = combinations * self.replicates
        if total_cases > self.budget.max_cases:
            raise ValueError(
                "El diseño experimental supera max_cases antes de realizar consultas."
            )
        return self

    def iter_cases(self):
        """Produce el producto cartesiano autorizado, incluido el réplica."""
        names = tuple(self.variables.keys())
        domains = tuple(self.variables[name].values for name in names)
        for replicate in range(self.replicates):
            for values in product(*domains):
                yield {**dict(zip(names, values, strict=True)), "replicate": replicate}
