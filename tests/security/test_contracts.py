import pytest
from pydantic import ValidationError

from blackbox_lab.core.contracts import InputObservation, RawDocument, SecurityPolicy
from blackbox_lab.execution.checkpoints import ExecutionState, RunCheckpoint


@pytest.mark.parametrize(
    "field",
    [
        "authorization_required",
        "data_redaction",
        "stop_on_budget_limit",
    ],
)
def test_security_controls_cannot_be_disabled(field):
    with pytest.raises(ValidationError):
        SecurityPolicy(**{field: False})


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


def test_raw_document_rejects_duplicate_keys():
    with pytest.raises(ValueError):
        RawDocument(canonical_json='{"cost": 1, "cost": 999}')


def test_checkpoint_completed_requires_all_cases():
    with pytest.raises(ValueError):
        RunCheckpoint(
            experiment_id="exp",
            run_id="run",
            state=ExecutionState.COMPLETED,
            completed_cases=0,
            total_cases=10,
        )


def test_input_observation_immutable_payload():
    doc = RawDocument(canonical_json='{"temperature": 25.5}')
    obs = InputObservation(raw_document=doc)
    assert obs.payload == {"temperature": 25.5}
    # Payload getter returns parsed copy, original doc remains untouched
    p = obs.payload
    p["temperature"] = 999
    assert obs.payload == {"temperature": 25.5}
