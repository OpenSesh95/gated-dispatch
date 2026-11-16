"""Prompt provenance (C-039): the prompt registry + run stamps.

The registry versions prompts like Leela atoms — supersede, never
overwrite. Records carry HASHES, not texts: registry texts are
access-ruled (prompts are IP and can carry compartmented material), so
the text lives only at its source and the registry proves identity by
hash. Three species register separately: system (standing prompts),
task (per-run task prompts), context (injected context recipes).

The run stamp completes a run's identity: model + task set + prompts +
decoding parameters. Until Treasury adopts the stamp as feed fields
(§7 pattern, flagged in the standard), stamps file in run records and
cite from bench summaries. Validity rule: a scored run without a
complete prompt stamp reads UNMEASURED.
"""

from __future__ import annotations

import hashlib
import json
import os
import time

SPECIES = ("system", "task", "context")
TEMPERATURE_CLASSES = ("deterministic", "low", "standard", "creative",
                       "provider-default")


def content_hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _read_registry(path: str) -> list[dict]:
    if not os.path.exists(path):
        return []
    with open(path, encoding="utf-8") as fh:
        return [json.loads(line) for line in fh if line.strip()]


def register(path: str, prompt_id: str, species: str, text: str,
             author: str, change: str, template_vars: list[str] | None = None,
             ts: str | None = None) -> dict:
    """Append the next version of a prompt. The text itself is never
    stored — only its hash; `change` is the changelog entry opening the
    version."""
    if species not in SPECIES:
        raise ValueError(f"species must be one of {SPECIES}, got {species!r}")
    rows = _read_registry(path)
    version = 1 + max((r["version"] for r in rows
                        if r["prompt_id"] == prompt_id), default=0)
    record = {
        "prompt_id": prompt_id, "species": species, "version": version,
        "sha256": content_hash(text), "author": author,
        "template_vars": list(template_vars or []),
        "changelog": change,
        "registered_at": ts or time.strftime("%Y-%m-%dT%H:%M:%SZ",
                                             time.gmtime()),
    }
    with open(path, "a", encoding="utf-8") as fh:
        fh.write(json.dumps(record, sort_keys=True) + "\n")
    return record


def lookup(path: str, prompt_id: str, version: int | None = None) -> dict | None:
    rows = [r for r in _read_registry(path) if r["prompt_id"] == prompt_id]
    if not rows:
        return None
    if version is None:
        return max(rows, key=lambda r: r["version"])
    return next((r for r in rows if r["version"] == version), None)


def verify_text(path: str, text: str) -> dict | None:
    """The registered record whose hash matches this text, or None.
    None is the TS-SEC provenance anomaly: an unregistered hash."""
    digest = content_hash(text)
    for record in _read_registry(path):
        if record["sha256"] == digest:
            return record
    return None


def provenance_status(path: str, text: str) -> dict:
    record = verify_text(path, text)
    if record is None:
        return {"registered": False, "anomaly": True,
                "reason": "prompt hash matches no registered version"}
    return {"registered": True, "anomaly": False,
            "prompt_id": record["prompt_id"],
            "version": record["version"], "species": record["species"]}


def build_stamp(entries: list[dict], temperature_class: str = "provider-default") -> dict:
    """Assemble a run stamp from resolved registry records.
    entries: [{record, ...}] as returned by lookup/register. The stamp
    carries id + version + hash per species present + decoding class."""
    if temperature_class not in TEMPERATURE_CLASSES:
        raise ValueError(f"unknown temperature class {temperature_class!r}")
    stamp = {"temperature_class": temperature_class, "prompts": {}}
    for record in entries:
        stamp["prompts"][record["species"]] = {
            "prompt_id": record["prompt_id"],
            "version": record["version"],
            "sha256": record["sha256"],
        }
    return stamp


def stamp_complete(stamp: dict | None, required_species: list[str]) -> bool:
    if not stamp:
        return False
    present = stamp.get("prompts", {})
    return all(species in present and present[species].get("sha256")
               for species in required_species)


def pairing_check(stamp_a: dict | None, stamp_b: dict | None) -> dict:
    """Prompt deltas as experiments (standard §4): two runs pair only if
    their prompt stamps are identical. A mid-bench prompt edit breaks
    the pairing, and the bench record says so through this check."""
    if stamp_a is None or stamp_b is None:
        return {"paired_valid": False,
                "reason": "a run in the pair carries no prompt stamp (UNMEASURED)"}
    if stamp_a.get("prompts") != stamp_b.get("prompts"):
        return {"paired_valid": False,
                "reason": "prompt stamps differ — the prompt delta is the "
                          "experiment; the runs do not pair"}
    if stamp_a.get("temperature_class") != stamp_b.get("temperature_class"):
        return {"paired_valid": False,
                "reason": "decoding temperature class differs across the pair"}
    return {"paired_valid": True, "reason": "prompt stamps identical"}


def run_validity(stamp: dict | None, scored: bool,
                 required_species: list[str] | None = None) -> str:
    """The validity rule: a scored run without a complete stamp reads
    UNMEASURED. Unscored runs are not judged by the rule."""
    if not scored:
        return "unscored"
    required = required_species or ["task"]
    return "stamped" if stamp_complete(stamp, required) else "UNMEASURED"
