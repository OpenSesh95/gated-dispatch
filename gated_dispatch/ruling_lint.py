"""Ruling conflict lint — ADVISORY form only (C-029 H-C1).

Before a ruling that edits chain membership · degrade order ·
probation states · dispositions · throttle rules takes effect,
a mechanical dry-run against the active rule set files any
collision on the ruling surface, before the tap. S-2 stays the
after-the-fact sensor; this lint is the before-the-fact read.
The lint's own miss rate files with its output.

The BLOCKING form is Council-bound (CB-C29-2). This module
never blocks, stops, or edits anything: it returns collisions
as data. A ruling proceeds on the owner's tap regardless.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone

from . import pricing, throttle as throttle_mod


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def lint_ruling(change: dict, state=None) -> dict:
    """Dry-run a proposed ruling change-set against the active
    rules. Change keys (all optional): chain_add · chain_remove ·
    chain_order · probation_add · probation_remove · repin
    ({from: to}) · throttle_rules ({model: {field: value}})."""
    collisions: list[dict] = []

    def hit(rule: str, detail: str):
        collisions.append({"rule": rule, "detail": detail})

    chain = list(throttle_mod.COMMODITY_CHAIN)
    for model in change.get("chain_add", []):
        if model not in throttle_mod.MODELS:
            hit("unregistered-in-chain",
                f"{model} has no throttle rule; the chain cannot fire it")
        elif (throttle_mod.MODELS[model].provider, model) \
                not in pricing.PRICES:
            hit("unpriced-in-chain", f"{model} carries no price entry")
        if state is not None and state.is_quarantined(model):
            hit("quarantined-in-chain",
                f"{model} stands quarantined in throttle state")
    for model in change.get("chain_remove", []):
        named_successor = (change.get("repin") or {}).get(model)
        if (model == chain[0] and not named_successor
                and not change.get("chain_order")):
            hit("headless-chain",
                f"removing the chain head {model} with no repin "
                "names no successor head")
    order = change.get("chain_order")
    if order is not None:
        dropped = [m for m in chain if m not in order]
        if dropped:
            hit("order-drops-member",
                f"the proposed order drops current members {dropped} "
                "without naming their removal")
        for model in order:
            if model not in throttle_mod.MODELS:
                hit("unregistered-in-chain",
                    f"order names {model}, which has no throttle rule")
    for old, new in (change.get("repin") or {}).items():
        if old == new:
            hit("repin-noop", f"repin maps {old} to itself")
        if new not in chain and new not in change.get("chain_add", []):
            hit("repin-target-invalid",
                f"repin target {new} is not in the chain")
    for model in change.get("probation_add", []):
        if model not in throttle_mod.MODELS:
            hit("probation-without-rule",
                f"{model} has no throttle rule; its probation "
                "trigger could never fire")
    for model, fields in (change.get("throttle_rules") or {}).items():
        if model not in throttle_mod.MODELS:
            hit("rule-for-unknown-model",
                f"throttle rule edit names {model}, not registered")
        if fields.get("concurrency", 1) < 1:
            hit("rule-out-of-range", f"{model} concurrency below 1")
        if fields.get("min_interval_s", 0) < 0:
            hit("rule-out-of-range", f"{model} min interval negative")
    return {"ts": _now_iso(), "advisory": True,
            "collisions": collisions,
            "clean": not collisions}


def file_lint(change: dict, findings_path: str, state=None) -> dict:
    """Run the lint and append any collisions as findings."""
    out = lint_ruling(change, state=state)
    if out["collisions"]:
        with open(findings_path, "a", encoding="utf-8") as fh:
            for c in out["collisions"]:
                fh.write(json.dumps({
                    "ts": out["ts"], "sensor": "H-C1-lint",
                    "class": "ruling-collision",
                    "fact": f"{c['rule']}: {c['detail']}",
                    "evidence": ["active rule set at lint time"],
                    "advisory": True,
                }, sort_keys=True) + "\n")
    return out
