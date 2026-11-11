"""Cost ledger: one JSONL row per run, whatever the outcome.

Rows record the prompt's SHA-256 and length, never the raw prompt, so
a ledger can be published as an ops receipt without leaking content.
Statuses: approved · rejected-verification · rejected-gate · error.
"""

import hashlib
import json
import os
from datetime import datetime, timezone

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
) -> dict:
    cost = 0.0
    if tokens_in or tokens_out:
        cost = round(estimate_cost_usd(model, tokens_in, tokens_out), 6)
    row = {
        "ticket": _next_ticket_id(path),
        "ts": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "model": model,
        "prompt_sha256": hashlib.sha256(prompt.encode("utf-8")).hexdigest(),
        "prompt_chars": len(prompt),
        "tokens_in": tokens_in,
        "tokens_out": tokens_out,
        "cost_usd": cost,
        "status": status,
        "checks": checks or {},
    }
    with open(path, "a", encoding="utf-8") as fh:
        fh.write(json.dumps(row, sort_keys=True) + "\n")
    return row
