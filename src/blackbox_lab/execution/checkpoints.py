import os
import re
import tempfile
from enum import Enum
from pathlib import Path
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field, model_validator

SAFE_ID_PATTERN = r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,63}$"


class ExecutionState(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    INTERRUPTED = "interrupted"


class RunCheckpoint(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
        frozen=True,
        allow_inf_nan=False,
        revalidate_instances="always",
    )

    experiment_id: str = Field(..., pattern=SAFE_ID_PATTERN)
    run_id: str = Field(..., pattern=SAFE_ID_PATTERN)
    state: ExecutionState
    completed_cases: int = Field(0, ge=0, strict=True)
    total_cases: int = Field(..., ge=1, le=10_000, strict=True)
    current_cost: float = Field(0.0, ge=0.0, le=10_000.0, strict=True)

    @model_validator(mode="after")
    def validate_cases(self) -> "RunCheckpoint":
        if self.completed_cases > self.total_cases:
            raise ValueError("completed_cases supera total_cases.")
        if (
            self.state == ExecutionState.COMPLETED
            and self.completed_cases != self.total_cases
        ):
            raise ValueError("Un checkpoint completado debe cubrir todos los casos.")
        return self


class CheckpointManager:
    def __init__(self, storage_dir: str = "./data/checkpoints"):
        self.storage_dir = Path(storage_dir).resolve()
        self.storage_dir.mkdir(parents=True, exist_ok=True)

    def _resolve_safe_path(self, run_id: str) -> Path:
        if not isinstance(run_id, str) or not re.fullmatch(SAFE_ID_PATTERN, run_id):
            raise ValueError(f"Identificador de ejecución inseguro o inválido: {run_id}")
        target_path = (self.storage_dir / f"{run_id}.json").resolve()
        try:
            target_path.relative_to(self.storage_dir)
        except ValueError as exc:
            raise ValueError("Acceso fuera del directorio autorizado de checkpoints.") from exc
        return target_path

    def save_checkpoint(self, checkpoint: RunCheckpoint):
        """Escritura atómica mediante archivo temporal, flush, fsync y replace."""
        target_path = self._resolve_safe_path(checkpoint.run_id)
        content = checkpoint.model_dump_json(indent=2)

        # Crear archivo temporal en el mismo directorio/filesystem para permitir replace atómico
        fd, tmp_path_str = tempfile.mkstemp(dir=self.storage_dir, prefix="ckpt_tmp_")
        tmp_path = Path(tmp_path_str)
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                f.write(content)
                f.flush()
                os.fsync(f.fileno())
            os.replace(tmp_path, target_path)
        except Exception:
            if tmp_path.exists():
                tmp_path.unlink()
            raise

    def load_checkpoint(self, run_id: str) -> Optional[RunCheckpoint]:
        target_path = self._resolve_safe_path(run_id)
        if not target_path.exists():
            return None
        with open(target_path, "rb") as handle:
            content = handle.read(64 * 1024 + 1)
        if len(content) > 64 * 1024:
            raise ValueError("Checkpoint demasiado grande.")
        checkpoint = RunCheckpoint.model_validate_json(content)
        if checkpoint.run_id != run_id:
            raise ValueError("La identidad del checkpoint no coincide.")
        return checkpoint
