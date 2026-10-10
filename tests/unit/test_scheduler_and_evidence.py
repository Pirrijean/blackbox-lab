import asyncio
from decimal import Decimal
import pytest

from blackbox_lab.adapters.simulator import DeterministicSimulatorAdapter
from blackbox_lab.core.contracts import BudgetPolicy, InputObservation, RawDocument, SecurityPolicy
from blackbox_lab.core.experiment import ExperimentConfig, Hypothesis, VariableDef
from blackbox_lab.execution.budgets import BudgetManager, BudgetExceededError
from blackbox_lab.execution.checkpoints import CheckpointManager
from blackbox_lab.execution.evidence import EvidenceStore
from blackbox_lab.execution.scheduler import ExperimentScheduler


TEST_HMAC_KEY = "test-key-which-is-long-enough-to-sign-evidence"


def test_budget_manager_decimal_accounting(tmp_path):
    storage = tmp_path / "budget_state.json"
    bm = BudgetManager(limit_usd=Decimal("2.50"), max_calls=5, storage_path=storage)

    res_id = bm.reserve(Decimal("1.00"))
    assert bm.remaining_budget_usd == Decimal("1.50")

    bm.confirm(res_id, actual_spend=Decimal("0.85"), tokens_used=200)
    assert bm.confirmed_spend_usd == Decimal("0.85")
    assert bm.remaining_budget_usd == Decimal("1.65")


def test_evidence_store_integrity(tmp_path):
    store = EvidenceStore(raw_storage_dir=tmp_path / "raw", signing_key=TEST_HMAC_KEY)
    input_obs = InputObservation(raw_document=RawDocument(canonical_json='{"x": 1.0}'))
    
    adapter = DeterministicSimulatorAdapter()
    output_obs = asyncio.run(adapter.execute(input_obs, request_id="req_test"))

    record = store.append_record("exp_test", input_obs, output_obs)
    assert store.verify_integrity(record) is True

    records = store.load_records("exp_test")
    assert len(records) == 1
    assert records[0].record_id == input_obs.id


def test_experiment_scheduler_runs_end_to_end(tmp_path):
    config = ExperimentConfig(
        id="test_exp_sched",
        version="1.0",
        objective="Prueba end-to-end con simulador",
        hypothesis=Hypothesis(
            description="Hipótesis local",
            expected_observable="Convergencia calculada",
        ),
        target_adapter="simulator",
        model_id="benchmark",
        variables={"x": VariableDef(values=[1.0, 2.0])},
        replicates=2,
        budget=BudgetPolicy(max_cases=4, max_cost_usd=1.0),
        security=SecurityPolicy(),
    )

    adapter = DeterministicSimulatorAdapter()
    scheduler = ExperimentScheduler(
        config=config,
        adapter=adapter,
        budget_manager=BudgetManager(
            limit_usd=Decimal("1.00"), max_calls=4, storage_path=tmp_path / "b.json"
        ),
        checkpoint_manager=CheckpointManager(storage_dir=tmp_path / "checkpoints"),
        evidence_store=EvidenceStore(raw_storage_dir=tmp_path / "raw", signing_key=TEST_HMAC_KEY),
    )

    result = asyncio.run(scheduler.run("run_sched_01"))
    assert result.state == "completed"
    assert result.cases_completed == 4
    assert "primary_metric" in result.metric_results
