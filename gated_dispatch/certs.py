"""Leg certification records (C-029 Group B, H-B1).

Every composition role — proposer · aggregator · verifier —
carries a per-leg golden set and a pass bar, per family. A leg
certifies by running its role set; the cert record is the
evidence: {leg, model, role, family, set_version, score, bar,
ticket, ts}. An uncertified leg cannot be composed: the TS-PRE
preflight checks each leg's cert record when the engagement
supplies a cert store.

Certification expires on: served-identity drift (a canary S-9
event naming the model) · the role set's version bump · a
scored failure attributed to the leg. Expiry is computed at
check time from the record + the caller's current facts; the
record itself is never edited (records are evidence).
"""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone

ROLES = ("proposer", "aggregator", "verifier")


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def record_cert(path: str, *, leg: str, model: str, role: str,
                family: str, set_version: str, score: float,
                bar: float, ticket: str) -> dict:
    if role not in ROLES:
        raise ValueError(f"unknown role {role!r}")
    rec = {"leg": leg, "model": model, "role": role,
           "family": family, "set_version": set_version,
           "score": score, "bar": bar, "ticket": ticket,
           "passed": score >= bar, "ts": _now_iso()}
    with open(path, "a", encoding="utf-8") as fh:
        fh.write(json.dumps(rec, sort_keys=True) + "\n")
    return rec


def load_certs(path: str) -> list[dict]:
    if not os.path.exists(path):
        return []
    with open(path, encoding="utf-8") as fh:
        return [json.loads(l) for l in fh if l.strip()]


def check_leg(certs: list[dict], *, model: str, role: str,
              set_version: str, drifted: set[str] | None = None,
              attributed_failure: bool = False) -> dict:
    """The cert status of one leg against current facts."""
    mine = [c for c in certs
            if c["model"] == model and c["role"] == role]
    if not mine:
        return {"status": "missing", "cert": None}
    cert = mine[-1]
    if not cert["passed"]:
        return {"status": "failed-bar", "cert": cert}
    if cert["set_version"] != set_version:
        return {"status": "stale-set-version", "cert": cert}
    if drifted and model in drifted:
        return {"status": "expired-drift", "cert": cert}
    if attributed_failure:
        return {"status": "expired-attribution", "cert": cert}
    return {"status": "certified", "cert": cert}
