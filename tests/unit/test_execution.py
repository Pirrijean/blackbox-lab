import pytest
from blackbox_lab.execution.checkpoints import CheckpointManager, RunCheckpoint, ExecutionState
from blackbox_lab.execution.retries import execute_with_retry, RetryPolicy

def test_checkpoint_save_load(tmp_path):
    manager = CheckpointManager(storage_dir=str(tmp_path))
    ckpt = RunCheckpoint(
        experiment_id="exp-1",
        run_id="run-1",
        state=ExecutionState.RUNNING,
        total_cases=10
    )
    # Probar escritura segura
    manager.save_checkpoint(ckpt)
    
    # Probar recuperación
    loaded = manager.load_checkpoint("run-1")
    assert loaded is not None
    assert loaded.state == ExecutionState.RUNNING
    assert loaded.total_cases == 10

def test_execute_with_retry():
    attempts = 0
    def faulty_func():
        nonlocal attempts
        attempts += 1
        if attempts < 3:
            raise ValueError("Fallo transitorio simulado")
        return "Éxito tras recuperación"

    policy = RetryPolicy(max_retries=3, base_delay_seconds=0.01)
    result = execute_with_retry(faulty_func, policy)
    
    # Verifica que superó el error transitorio y retomó la ejecución
    assert result == "Éxito tras recuperación"
    assert attempts == 3
