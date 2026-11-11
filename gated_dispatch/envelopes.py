"""Budget-regime envelopes and lane sub-ceilings (C-007 table, T=$155).

Every dispatch names the envelope it draws from and the lane it runs
on. Before dispatch, month-to-date spend is read from the ledger:
- at 100% of an envelope or a lane sub-ceiling, the class hard-stops
  (other classes and lanes continue);
- at 90%, work holds for the owner's word (an acknowledged hold may
  proceed, and the acknowledgement is recorded on the ticket);
- the $155 aggregate backstop stops all non-gated dispatch;
- ci-local is metered but uncapped until a baseline exists (C-007);
- an unclassed dispatch is refused — envelope is a required field.

Figures are the C-007 design table as applied 2026-11-11; they are
re-derived after the first metered month.
"""

import json
import os
from datetime import datetime, timezone

ENVELOPES_USD = {
    "frontier": 121.33,
    "sweeps": 10.92,
    "open-weight": 15.00,
    "health": 7.75,
    "ci-local": 0.00,
}

LANE_CEILINGS_USD = {
    "anthropic": 75.00,
    "google": 35.00,
    "xai": 30.00,
    "open": 15.00,
}

BACKSTOP_USD = 155.00
HOLD_FRACTION = 0.90
OWNER_MINUTE_RATE_USD = 2.00  # interim rate, applied 2026-11-11 (NS-6)


def month_to_date(ledger_path: str) -> dict:
    """Sum this UTC month's ticketed cost by envelope, lane, and total."""
    month = datetime.now(timezone.utc).strftime("%Y-%m")
    totals = {"envelopes": {}, "lanes": {}, "total": 0.0}
    if not os.path.exists(ledger_path):
        return totals
    with open(ledger_path, encoding="utf-8") as fh:
        for line in fh:
            try:
                row = json.loads(line)
            except ValueError:
                continue
            if not str(row.get("ts", "")).startswith(month):
                continue
            cost = float(row.get("cost_usd", 0) or 0)
            env = row.get("envelope")
            lane = row.get("lane")
            if env:
                totals["envelopes"][env] = totals["envelopes"].get(env, 0.0) + cost
            if lane:
                totals["lanes"][lane] = totals["lanes"].get(lane, 0.0) + cost
            totals["total"] += cost
    return totals


def preflight(ledger_path: str, envelope: str, lane: str) -> dict:
    """Decide whether a dispatch may proceed: ok | hold | blocked.

    The returned snapshot is written onto the ticket either way, so a
    refusal is as much a ledger event as a dispatch.
    """
    if envelope not in ENVELOPES_USD:
        return {"decision": "blocked", "reason": f"unknown envelope {envelope!r}"}
    mtd = month_to_date(ledger_path)
    env_spent = mtd["envelopes"].get(envelope, 0.0)
    lane_spent = mtd["lanes"].get(lane, 0.0)
    snapshot = {
        "envelope": envelope,
        "lane": lane,
        "envelope_mtd_usd": round(env_spent, 6),
        "lane_mtd_usd": round(lane_spent, 6),
        "backstop_mtd_usd": round(mtd["total"], 6),
    }
    if mtd["total"] >= BACKSTOP_USD:
        return {**snapshot, "decision": "blocked", "reason": "aggregate backstop reached"}
    if envelope != "ci-local":
        cap = ENVELOPES_USD[envelope]
        if env_spent >= cap:
            return {**snapshot, "decision": "blocked", "reason": f"envelope {envelope} exhausted"}
        lane_cap = LANE_CEILINGS_USD.get(lane)
        if lane_cap is not None and lane_spent >= lane_cap:
            return {**snapshot, "decision": "blocked", "reason": f"lane {lane} ceiling reached"}
        if (
            env_spent >= HOLD_FRACTION * cap
            or (lane_cap is not None and lane_spent >= HOLD_FRACTION * lane_cap)
            or mtd["total"] >= HOLD_FRACTION * BACKSTOP_USD
        ):
            return {**snapshot, "decision": "hold", "reason": "90% hold — owner's word required"}
    return {**snapshot, "decision": "ok", "reason": ""}
