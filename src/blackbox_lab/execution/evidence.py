"""Append-only evidence with a chained HMAC integrity seal.

The HMAC key is deliberately supplied outside the repository.  A filesystem
permission alone cannot make an evidence file immutable to the same process
that analyses it; the seal makes unauthorised rewrites detectable as long as
the key is held by the evidence writer/KMS boundary.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import os
import re
from pathlib import Path
from typing import Iterable

from pydantic import BaseModel, ConfigDict, Field

from blackbox_lab.core.contracts import InputObservation, OutputObservation

SAFE_ID_PATTERN = r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,63}$"


class EvidenceIntegrityError(ValueError):
    """Evidence is missing, altered, or not part of the expected chain."""


class EvidenceRecord(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, allow_inf_nan=False)

    record_id: str = Field(..., pattern=SAFE_ID_PATTERN)
    experiment_id: str = Field(..., pattern=SAFE_ID_PATTERN)
    raw_input_json: str
    raw_output_json: str
    cost_usd: float | None
    timestamp_utc: str
    previous_hash: str | None = None
    record_hash: str
    hmac_sha256: str


class EvidenceStore:
    """One writer for raw evidence; readers only receive verified records."""

    def __init__(self, raw_storage_dir: Path | str = "./data/raw", *, signing_key: str | bytes | None = None):
        key = signing_key
        if key is None:
            key = os.environ.get("BLACKBOX_EVIDENCE_HMAC_KEY")
        if isinstance(key, str):
            key = key.encode("utf-8")
        if not isinstance(key, bytes) or len(key) < 32:
            raise ValueError(
                "Se requiere BLACKBOX_EVIDENCE_HMAC_KEY de al menos 32 bytes para escribir evidencia."
            )

        self._key = key
        self.raw_dir = Path(raw_storage_dir).resolve()
        self.raw_dir.mkdir(parents=True, exist_ok=True)

    @staticmethod
    def _canonical(value: dict) -> bytes:
        return json.dumps(
            value, ensure_ascii=False, allow_nan=False, sort_keys=True, separators=(",", ":")
        ).encode("utf-8")

    @staticmethod
    def _record_payload(record: EvidenceRecord | dict) -> dict:
        data = record if isinstance(record, dict) else record.model_dump()
        return {
            "record_id": data["record_id"],
            "experiment_id": data["experiment_id"],
            "raw_input_json": data["raw_input_json"],
            "raw_output_json": data["raw_output_json"],
            "cost_usd": data["cost_usd"],
            "timestamp_utc": data["timestamp_utc"],
            "previous_hash": data["previous_hash"],
        }

    def _seal(self, payload: dict) -> tuple[str, str]:
        encoded = self._canonical(payload)
        record_hash = hashlib.sha256(encoded).hexdigest()
        signature = hmac.new(self._key, record_hash.encode("ascii"), hashlib.sha256).hexdigest()
        return record_hash, signature

    def _path(self, experiment_id: str) -> Path:
        if not re.fullmatch(SAFE_ID_PATTERN, experiment_id):
            raise ValueError("Identificador de experimento inseguro.")
        path = (self.raw_dir / f"{experiment_id}_evidence.jsonl").resolve()
        try:
            path.relative_to(self.raw_dir)
        except ValueError as exc:
            raise ValueError("Ruta de evidencia fuera del directorio autorizado.") from exc
        if path.exists() and path.is_symlink():
            raise EvidenceIntegrityError("La evidencia no puede ser un enlace simbólico.")
        return path

    def append_record(
        self,
        experiment_id: str,
        input_obs: InputObservation,
        output_obs: OutputObservation,
        *,
        record_id: str | None = None,
    ) -> EvidenceRecord:
        """Append a fully sealed record and fsync it before returning."""
        if output_obs.input_id != input_obs.id:
            raise EvidenceIntegrityError("La respuesta no pertenece a la entrada autorizada.")

        path = self._path(experiment_id)
        previous_hash = None
        if path.exists():
            records = self.load_records(experiment_id)
            previous_hash = records[-1].record_hash if records else None

        payload = {
            "record_id": record_id or input_obs.id,
            "experiment_id": experiment_id,
            "raw_input_json": input_obs.raw_document.canonical_json,
            "raw_output_json": (
                output_obs.raw_document.canonical_json if output_obs.raw_document else "{}"
            ),
            "cost_usd": output_obs.cost,
            "timestamp_utc": output_obs.timestamp.isoformat(),
            "previous_hash": previous_hash,
        }
        record_hash, signature = self._seal(payload)
        record = EvidenceRecord(**payload, record_hash=record_hash, hmac_sha256=signature)

        flags = os.O_CREAT | os.O_APPEND | os.O_WRONLY
        flags |= getattr(os, "O_NOFOLLOW", 0)
        descriptor = os.open(path, flags, 0o600)
        try:
            encoded = record.model_dump_json().encode("utf-8") + b"\n"
            view = memoryview(encoded)
            while view:
                written = os.write(descriptor, view)
                view = view[written:]
            os.fsync(descriptor)
        finally:
            os.close(descriptor)
        return record

    def load_records(self, experiment_id: str) -> list[EvidenceRecord]:
        path = self._path(experiment_id)
        if not path.exists():
            return []
        if path.is_symlink():
            raise EvidenceIntegrityError("La evidencia no puede ser un enlace simbólico.")

        records: list[EvidenceRecord] = []
        with path.open("rb") as handle:
            for raw_line in handle:
                if not raw_line.strip():
                    continue
                try:
                    records.append(EvidenceRecord.model_validate_json(raw_line))
                except Exception as exc:
                    raise EvidenceIntegrityError("Registro de evidencia malformado.") from exc
        self.verify_chain(records)
        return records

    def verify_integrity(self, record: EvidenceRecord) -> bool:
        payload = self._record_payload(record)
        record_hash, signature = self._seal(payload)
        return hmac.compare_digest(record.record_hash, record_hash) and hmac.compare_digest(
            record.hmac_sha256, signature
        )

    def verify_chain(self, records: Iterable[EvidenceRecord]) -> None:
        previous_hash = None
        seen_ids: set[str] = set()
        for record in records:
            if record.record_id in seen_ids:
                raise EvidenceIntegrityError("Identificador de evidencia duplicado.")
            if record.previous_hash != previous_hash or not self.verify_integrity(record):
                raise EvidenceIntegrityError("Cadena de evidencia alterada o incompleta.")
            seen_ids.add(record.record_id)
            previous_hash = record.record_hash
