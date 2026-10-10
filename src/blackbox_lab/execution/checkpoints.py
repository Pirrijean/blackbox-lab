from pydantic import BaseModel
from typing import Optional
from enum import Enum
import json
import os

class ExecutionState(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    INTERRUPTED = "interrupted"

class RunCheckpoint(BaseModel):
    experiment_id: str
    run_id: str
    state: ExecutionState
    completed_cases: int = 0
    total_cases: int
    current_cost: float = 0.0

class CheckpointManager:
    def __init__(self, storage_dir: str = "./data/checkpoints"):
        self.storage_dir = storage_dir
        os.makedirs(storage_dir, exist_ok=True)

    def save_checkpoint(self, checkpoint: RunCheckpoint):
        path = os.path.join(self.storage_dir, f"{checkpoint.run_id}.json")
        with open(path, "w") as f:
            f.write(checkpoint.model_dump_json(indent=2))

    def load_checkpoint(self, run_id: str) -> Optional[RunCheckpoint]:
        path = os.path.join(self.storage_dir, f"{run_id}.json")
        if not os.path.exists(path):
            return None
        with open(path, "r") as f:
            return RunCheckpoint.model_validate_json(f.read())
