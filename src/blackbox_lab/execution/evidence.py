import hashlib
import json
from pathlib import Path
from typing import Dict, List, Optional
from pydantic import BaseModel, ConfigDict, Field

from blackbox_lab.core.contracts import InputObservation, OutputObservation


class EvidenceRecord(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    record_id: str
    experiment_id: str
    sha256_hash: str
    raw_input_json: str
    raw_output_json: str
    cost_usd: Optional[float] = 0.0
    timestamp_utc: str


class EvidenceStore:
    """Almacén de evidencia original inmutable y append-only (Fase 4 P0)."""

    def __init__(self, raw_storage_dir: Path | str = "./data/raw"):
        self.raw_dir = Path(raw_storage_dir).resolve()
        self.raw_dir.mkdir(parents=True, exist_ok=True)

    def append_record(
        self,
        experiment_id: str,
        input_obs: InputObservation,
        output_obs: OutputObservation,
    ) -> EvidenceRecord:
        """Anexa un par entrada/salida a la evidencia inmutable calculando su hash de integridad."""
        input_json = input_obs.raw_document.canonical_json
        output_json = output_obs.raw_document.canonical_json if output_obs.raw_document else "{}"

        content_to_hash = f"{input_obs.id}:{input_json}|{output_obs.input_id}:{output_json}"
        record_hash = hashlib.sha256(content_to_hash.encode("utf-8")).hexdigest()

        record = EvidenceRecord(
            record_id=input_obs.id,
            experiment_id=experiment_id,
            sha256_hash=record_hash,
            raw_input_json=input_json,
            raw_output_json=output_json,
            cost_usd=output_obs.cost if output_obs.cost is not None else 0.0,
            timestamp_utc=output_obs.timestamp.isoformat(),
        )

        file_path = self.raw_dir / f"{experiment_id}_evidence.jsonl"
        with open(file_path, "a", encoding="utf-8") as f:
            f.write(record.model_dump_json() + "\n")

        return record

    def load_records(self, experiment_id: str) -> List[EvidenceRecord]:
        file_path = self.raw_dir / f"{experiment_id}_evidence.jsonl"
        if not file_path.exists():
            return []
        records = []
        with open(file_path, "r", encoding="utf-8") as f:
            for line in f:
                if line.strip():
                    records.append(EvidenceRecord.model_validate_json(line))
        return records

    def verify_integrity(self, record: EvidenceRecord) -> bool:
        """Verifica que los datos no hayan sido alterados en disco."""
        content = f"{record.record_id}:{record.raw_input_json}|{record.record_id}:{record.raw_output_json}"
        expected_hash = hashlib.sha256(content.encode("utf-8")).hexdigest()
        return record.sha256_hash == expected_hash
