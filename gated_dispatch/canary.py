"""Served-model canary probes (C-029 Group A, H-A2 · sensor S-9).

One minimal named-mode dispatch per seated id on the Sunday
cycle, plus a spot canary on any served!=requested feed event.
Served != requested files a drift finding (sensor S-9, class
drift-served) naming the pair, the feed evidence, and the
disposition options — re-pin · alias-quarantine (the R-2
precedent) · map correction. The canary never edits a map.
A recorded drift ENDING also files: release-condition evidence
accrues mechanically.

Env tag: the canary is a test-program probe; its runs carry
env=test. Open-weight ids probe per seat (local · gcp) — the
local seat is skipped while its lane is staged (Track A); a
skipped seat prints in the run summary, never as a finding.
"""

from __future__ import annotations

import json
import os
import time
from datetime import datetime, timezone

from . import cli as cli_mod
from . import throttle as throttle_mod

PROMPT = "Reply with exactly: lane live"
SKIP_PROVIDERS = {"local"}  # lane staged (Track A) — not a finding


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def seated_ids() -> list[tuple[str, str]]:
    """(provider, model) pairs for every allowlisted id."""
    pairs = []
    for model, rule in sorted(throttle_mod.MODELS.items()):
        pairs.append((rule.provider, model))
        if rule.provider == "local":
            pairs.append(("gcp", model))  # the mirror seat
    return pairs


def run_canary(ledger_path: str, findings_path: str,
               state_path: str | None = None,
               pairs: list[tuple[str, str]] | None = None,
               transport=None) -> dict:
    state_path = state_path or (ledger_path + ".canary-state.json")
    prior_drifting: set[str] = set()
    if os.path.exists(state_path):
        with open(state_path, encoding="utf-8") as fh:
            prior_drifting = set(json.load(fh).get("drifting", []))
    findings: list[dict] = []
    results: list[dict] = []
    drifting: set[str] = set()
    for provider, model in (pairs or seated_ids()):
        key = f"{provider}/{model}"
        if provider in SKIP_PROVIDERS:
            results.append({"seat": key, "result": "skipped-lane-staged"})
            continue
        row = cli_mod.run(
            PROMPT, model, ledger_path=ledger_path, provider=provider,
            loop_class="panel", seat_mode="named", env="test",
            auto_approve=True, transport=transport)
        served = (row.get("checks") or {}).get("model")
        if row["status"] == "approved" and row.get("model_match"):
            results.append({"seat": key, "result": "ok",
                            "ticket": row["ticket"]})
        elif row["status"] == "approved" or served:
            drifting.add(key)
            findings.append({
                "sensor": "S-9", "class": "drift-served",
                "fact": (f"canary drift: {key} served as {served} "
                         f"(ticket {row['ticket']})"),
                "evidence": [ledger_path],
                "options": ["re-pin", "alias-quarantine", "map correction"],
            })
            results.append({"seat": key, "result": "drift",
                            "served": served, "ticket": row["ticket"]})
        else:
            results.append({"seat": key, "result": "error",
                            "status": row["status"],
                            "ticket": row["ticket"]})
    for key in sorted(prior_drifting - drifting):
        findings.append({
            "sensor": "S-9", "class": "drift-served",
            "fact": f"canary drift ENDED: {key} serves as itself again",
            "evidence": [ledger_path],
            "options": ["release-condition evidence (R-2 accrual)"],
        })
    if findings:
        with open(findings_path, "a", encoding="utf-8") as fh:
            for finding in findings:
                fh.write(json.dumps(
                    {"ts": _now_iso(), **finding}, sort_keys=True) + "\n")
    with open(state_path, "w", encoding="utf-8") as fh:
        json.dump({"drifting": sorted(drifting), "ts": _now_iso()}, fh)
    return {"ts": _now_iso(), "results": results, "findings": findings,
            "drifting": sorted(drifting)}


def main(argv=None) -> int:
    import argparse
    parser = argparse.ArgumentParser(prog="gated_dispatch.canary")
    parser.add_argument("--ledger", default="canary.jsonl")
    parser.add_argument("--findings", default="canary-findings.jsonl")
    args = parser.parse_args(argv)
    out = run_canary(args.ledger, args.findings)
    print(json.dumps(out, indent=1, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
