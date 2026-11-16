"""Judge calibration (C-041 R1; C-029 H-D1 machinery).

Every instrument that scores a paid bench — a judge seat, a scorer
configuration, the form gate — carries a calibration record measured
against a filed gold set: agreement + per-class error rates (false
accepts printed separately; they are the dangerous class). A bench
summary whose judge has no current calibration record prints its
scores UNCALIBRATED. A judge stood down for divergence (C-029 Group D)
voids the scores it produced to provisional on the spot.

Records are append-only; standing down is a new record, never an edit.
"""

from __future__ import annotations

import json
import os
import time


def _read(path: str) -> list[dict]:
    if not os.path.exists(path):
        return []
    with open(path, encoding="utf-8") as fh:
        return [json.loads(line) for line in fh if line.strip()]


def measure(verdicts: list[str], golds: list[str]) -> dict:
    """Agreement + per-class error rates for one instrument over a
    gold set. Classes are ACCEPT / REJECT."""
    if len(verdicts) != len(golds) or not golds:
        raise ValueError("verdicts and golds must align and be non-empty")
    n = len(golds)
    agree = sum(1 for v, g in zip(verdicts, golds) if v == g)
    gold_accept = [i for i, g in enumerate(golds) if g == "ACCEPT"]
    gold_reject = [i for i, g in enumerate(golds) if g == "REJECT"]
    false_accept = sum(1 for i in gold_reject if verdicts[i] == "ACCEPT")
    false_reject = sum(1 for i in gold_accept if verdicts[i] == "REJECT")
    return {
        "n": n,
        "agreement": round(agree / n, 4),
        "false_accept_rate": (round(false_accept / len(gold_reject), 4)
                              if gold_reject else None),
        "false_reject_rate": (round(false_reject / len(gold_accept), 4)
                              if gold_accept else None),
        "false_accepts": false_accept, "false_rejects": false_reject,
    }


def record(path: str, instrument: str, kind: str, gold_set: str,
           metrics: dict, status: str = "measured",
           ts: str | None = None) -> dict:
    row = {"instrument": instrument, "kind": kind, "gold_set": gold_set,
           "status": status, **metrics,
           "ts": ts or time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())}
    with open(path, "a", encoding="utf-8") as fh:
        fh.write(json.dumps(row, sort_keys=True) + "\n")
    return row


def stand_down(path: str, instrument: str, reason: str,
               ts: str | None = None) -> dict:
    row = {"instrument": instrument, "kind": "judge", "gold_set": None,
           "status": "stood-down", "reason": reason, "n": 0,
           "agreement": None, "false_accept_rate": None,
           "false_reject_rate": None,
           "ts": ts or time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())}
    with open(path, "a", encoding="utf-8") as fh:
        fh.write(json.dumps(row, sort_keys=True) + "\n")
    return row


def check(path: str, instrument: str) -> dict:
    """The instrument's current calibration state: the latest record,
    or UNCALIBRATED when none exists."""
    rows = [r for r in _read(path) if r["instrument"] == instrument]
    if not rows:
        return {"instrument": instrument, "status": "UNCALIBRATED"}
    return rows[-1]
