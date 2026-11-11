"""Cost ledger: one JSONL row per run, whatever the outcome.

Rows record the prompt's SHA-256 and length, never the raw prompt, so
a ledger can be published as an ops receipt without leaking content.

STD-0 ticket fields (v0.2.0): every row is a complete metered ticket —
provider, model requested and served (a mismatch is flagged, never
silently accepted), input/output tokens taken from the API response's
usage fields, cost computed at published rates, the budget envelope
and lane it drew from with month-to-date snapshots, and the
owner-minute accounting for any human gate (elapsed shown-to-decision,
clamped; interim rate $2.00/min). Refusals and holds are rows too.
"""

import hashlib
import json
import os
from datetime import datetime, timezone

from . import envelopes as envelopes_mod
from .pricing import estimate_cost_usd


def _next_ticket_id(path: str) -> str:
    day = datetime.now(timezone.utc).strftime("%Y%m%d")
    n = 0
    if os.path.exists(path):
        with open(path, encoding="utf-8") as fh:
            n = sum(1 for _ in fh)
    return f"GD-{day}-{n + 1:04d}"


def append_row(
    path: str,
    *,
    prompt: str,
    model: str,
    tokens_in: int,
    tokens_out: int,
    status: str,
    checks: dict | None = None,
    provider: str = "",
    model_served: str = "",
    envelope: str = "",
    lane: str = "",
    snapshot: dict | None = None,
    owner_minutes: float = 0.0,
    gate: dict | None = None,
) -> dict:
    cost = 0.0
    if (tokens_in or tokens_out) and provider:
        cost = round(estimate_cost_usd(provider, model_served or model, tokens_in, tokens_out), 6)
    snapshot = snapshot or {}
    row = {
        "ticket": _next_ticket_id(path),
        "ts": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "provider": provider,
        "model": model,
        "model_served": model_served or model,
        "model_match": (model_served or model) == model,
        "prompt_sha256": hashlib.sha256(prompt.encode("utf-8")).hexdigest(),
        "prompt_chars": len(prompt),
        "tokens_in": tokens_in,
        "tokens_out": tokens_out,
        "tokens_source": "api_usage" if (tokens_in or tokens_out) else "none",
        "cost_usd": cost,
        "envelope": envelope,
        "lane": lane,
        "envelope_mtd_usd": snapshot.get("envelope_mtd_usd"),
        "lane_mtd_usd": snapshot.get("lane_mtd_usd"),
        "backstop_mtd_usd": snapshot.get("backstop_mtd_usd"),
        "owner_minutes": round(owner_minutes, 4),
        "owner_minute_rate_usd": envelopes_mod.OWNER_MINUTE_RATE_USD,
        "owner_minute_usd": round(owner_minutes * envelopes_mod.OWNER_MINUTE_RATE_USD, 6),
        "gate": gate or {},
        "status": status,
        "checks": checks or {},
    }
    with open(path, "a", encoding="utf-8") as fh:
        fh.write(json.dumps(row, sort_keys=True) + "\n")
    return row
