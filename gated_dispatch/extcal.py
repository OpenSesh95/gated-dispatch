"""External calibration (C-043): the source registry + snapshot store.

External benchmarks are PRIORS: they propose, local measurements
dispose, and no source seats a model by itself. Every external record
carries the full provenance field set or it does not enter the store:
source · publication + retrieval timestamps · methodology/version ·
units · model-id mapping · access/license terms · confidence.

Lawful access only, on the face of every source record: terms and
paywalls are respected; a paid source is his separate tap — a source
that turns out paywalled files as REGISTERED-NOT-COLLECTED with its
terms noted, never scraped around.

Snapshots are immutable (append-only). The WS-4 landing shape is
Treasury's as schema owner (§7 pattern); until acceptance, snapshots
file here in the same field shape.
"""

from __future__ import annotations

import json
import os
import time

REQUIRED_FIELDS = (
    "source", "source_record_id", "published_at", "retrieved_at",
    "methodology", "units", "model_id_raw", "model_id_mapped",
    "mapping_confidence", "access_terms", "confidence", "metrics",
)

SOURCE_STATES = ("COLLECTED", "REGISTERED-NOT-COLLECTED", "REGISTERED")


def validate_record(record: dict) -> list[str]:
    """The provenance gate: the list of missing/invalid fields.
    A record with a non-empty list does not enter the store."""
    problems = [f"missing:{f}" for f in REQUIRED_FIELDS
                if record.get(f) in (None, "")]
    if record.get("confidence") not in ("VERIFIED", "EXPECTED", "ASSUMED"):
        problems.append("confidence must be VERIFIED/EXPECTED/ASSUMED")
    return problems


def append_snapshot(path: str, record: dict) -> dict:
    problems = validate_record(record)
    if problems:
        raise ValueError(f"external record refused: {problems}")
    with open(path, "a", encoding="utf-8") as fh:
        fh.write(json.dumps(record, sort_keys=True) + "\n")
    return record


def shrink(prior: float, local: float | None, n: int,
           prior_strength: float = 5.0) -> dict:
    """Hierarchical shrinkage (P1): the external prior's weight decays
    as the local sample grows. weight_local = n / (n + strength).
    With no local measurement the prior stands at full weight and
    reads as a prior — it never silently becomes a measurement."""
    if local is None or n <= 0:
        return {"estimate": prior, "local_weight": 0.0,
                "basis": "prior-only (no local measurement)"}
    w = n / (n + prior_strength)
    return {"estimate": round(w * local + (1 - w) * prior, 4),
            "local_weight": round(w, 4),
            "basis": f"shrunk: local n={n}, prior strength {prior_strength}"}


def now_iso() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
