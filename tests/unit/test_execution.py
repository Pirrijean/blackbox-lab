import asyncio
import pytest
from blackbox_lab.execution.checkpoints import (
    CheckpointManager,
    ExecutionState,
    RunCheckpoint,
)
from blackbox_lab.execution.retries import (
    RetryPolicy,
    TransientReadError,
    execute_with_retry,
)


def test_checkpoint_save_load_and_traversal(tmp_path):
    manager = CheckpointManager(storage_dir=str(tmp_path))
    ckpt = RunCheckpoint(
        experiment_id="exp-1",
        run_id="run-1",
        state=ExecutionState.RUNNING,
        completed_cases=5,
        total_cases=10,
    )
    # Probar escritura atómica
    manager.save_checkpoint(ckpt)

    # Probar recuperación
    loaded = manager.load_checkpoint("run-1")
    assert loaded is not None
    assert loaded.state == ExecutionState.RUNNING
    assert loaded.completed_cases == 5
    assert loaded.total_cases == 10

    # Probar rechazo de path traversal
    with pytest.raises(ValueError):
        manager.load_checkpoint("../../etc/passwd")


def test_checkpoint_cases_validation():
    with pytest.raises(ValueError):
        RunCheckpoint(
            experiment_id="exp-1",
            run_id="run-1",
            state=ExecutionState.RUNNING,
            completed_cases=11,  # Mayor que total_cases
            total_cases=10,
        )


def test_validation_error_is_not_retried():
    attempts = 0

    async def invalid():
        nonlocal attempts
        attempts += 1
        raise ValueError("Entrada inválida")

    with pytest.raises(ValueError):
        asyncio.run(
            execute_with_retry(
                invalid,
                RetryPolicy(),
                safe_to_repeat=True,
            )
        )

    assert attempts == 1


def test_uncertain_operation_is_not_retried():
    attempts = 0

    async def operation():
        nonlocal attempts
        attempts += 1
        raise TransientReadError("Resultado desconocido")

    with pytest.raises(TransientReadError):
        asyncio.run(execute_with_retry(operation, RetryPolicy()))

    assert attempts == 1


def test_safe_read_has_bounded_retries():
    attempts = 0

    async def read():
        nonlocal attempts
        attempts += 1
        if attempts < 3:
            raise TransientReadError("Fallo temporal")
        return "ok"

    result = asyncio.run(
        execute_with_retry(
            read,
            RetryPolicy(max_retries=2, base_delay_seconds=0),
            safe_to_repeat=True,
        )
    )

    assert result == "ok"
    assert attempts == 3


def test_safe_to_repeat_requires_strict_bool():
    async def dummy():
        return 1

    with pytest.raises(ValueError, match="safe_to_repeat debe ser un booleano real"):
        asyncio.run(
            execute_with_retry(
                dummy,
                RetryPolicy(),
                safe_to_repeat=1,  # int not bool
            )
        )


def test_checkpoint_load_run_id_mismatch(tmp_path):
    manager = CheckpointManager(storage_dir=str(tmp_path))
    ckpt = RunCheckpoint(
        experiment_id="exp-1",
        run_id="run-actual",
        state=ExecutionState.RUNNING,
        completed_cases=1,
        total_cases=2,
    )
    # Save manually under mismatched filename
    fake_file = tmp_path / "run-fake.json"
    fake_file.write_text(ckpt.model_dump_json(), encoding="utf-8")

    with pytest.raises(ValueError, match="La identidad del checkpoint no coincide"):
        manager.load_checkpoint("run-fake")

