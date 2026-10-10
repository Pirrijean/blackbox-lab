import pytest
from pydantic import ValidationError

from blackbox_lab.core.contracts import (
    BudgetPolicy,
    InputObservation,
    OutputObservation,
    RawDocument,
    SecurityPolicy,
)
from blackbox_lab.execution.checkpoints import ExecutionState, RunCheckpoint


def test_payload_changes_do_not_modify_snapshot():
    observation = InputObservation(
        raw_document=RawDocument(
            canonical_json='{"nested":{"value":1}}'
        )
    )

    copy = observation.payload
    copy["nested"]["value"] = 999

    assert observation.payload["nested"]["value"] == 1


@pytest.mark.parametrize(
    "document",
    [
        '{"x":NaN}',
        '{"x":Infinity}',
        '{"x":1,"x":2}',
        '{"nested":{"x":1,"x":2}}',
    ],
)
def test_invalid_json_is_rejected(document):
    with pytest.raises(ValueError):
        RawDocument(canonical_json=document)


@pytest.mark.parametrize(
    "field",
    [
        "authorization_required",
        "data_redaction",
        "stop_on_budget_limit",
    ],
)
def test_security_cannot_be_disabled(field):
    with pytest.raises(ValidationError):
        SecurityPolicy(**{field: False})


def test_boolean_is_not_a_case_limit():
    with pytest.raises(ValidationError):
        BudgetPolicy(max_cases=True)


def test_success_requires_evidence():
    with pytest.raises(ValidationError):
        OutputObservation(input_id="input-1", status="success")


def test_unknown_cost_is_not_zero():
    output = OutputObservation(
        input_id="input-1",
        status="failure",
        error_code="transport",
    )
    assert output.cost is None


@pytest.mark.parametrize("value", [float("inf"), float("nan")])
def test_checkpoint_rejects_nonfinite_cost(value):
    with pytest.raises(ValidationError):
        RunCheckpoint(
            experiment_id="exp",
            run_id="run",
            state=ExecutionState.RUNNING,
            total_cases=1,
            current_cost=value,
        )


def test_checkpoint_completed_requires_all_cases():
    with pytest.raises(ValueError):
        RunCheckpoint(
            experiment_id="exp",
            run_id="run",
            state=ExecutionState.COMPLETED,
            completed_cases=0,
            total_cases=10,
        )
