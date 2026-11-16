"""Live-cost routing (C-042 — the ADOPTED rule, his tap 2026-11-12).

No dispatch resolves without a live expected-cost computation. The
objective is expected COST PER SUCCESSFUL LOOP; quality floors and
the A1 objective order bind as constraints — cost optimizes subject
to them, never instead of them.

Expected cost per candidate = (est. input tokens x live in-price,
cache-adjusted where the provider prices a cached prefix) + (class
contract cap x live out-price), divided by the seat's MEASURED
success rate on the class. A seat with no measured rate prices at
its EXPECTED label — and the stamp says so; an unlabeled expected
price is a defect.

The lambda shadow-pricing multiplier is a RATIFIED parameter. Until
a curve is ratified through the loop's adoption path, the router
runs lambda-NEUTRAL (1.0) and the stamp says so.

Failure posture: stale or unavailable live pricing never blocks
production — resolve falls back to the static mapping and the stamp
carries PRICING_STALE on its face.
"""

from __future__ import annotations

import json
import os

from . import lanes as lanes_mod
from . import pricing as pricing_mod
from . import throttle as throttle_mod

# Cached-input rates where the provider publishes them (USD per 1M).
CACHED_INPUT_RATES = {
    "grok-4.20-0309-reasoning": 0.20,
    "grok-4.20-0309-non-reasoning": 0.20,
    "grok-4.20-multi-agent-0309": 0.20,
}

POOL_FREE_LIMIT = 1000  # OpenRouter free requests/day at $10+ lifetime


def load_success_rates(path: str) -> dict:
    if not os.path.exists(path):
        return {}
    with open(path, encoding="utf-8") as fh:
        return json.load(fh).get("rates", {})


def measured_rate(rates: dict, model: str, loop_class: str) -> float | None:
    row = rates.get(f"{model}|{loop_class}")
    return row["rate"] if row else None


def estimate_input_tokens(prompt: str) -> int:
    """A labeled estimate: ~4 chars per token. The stamp carries the
    basis; the figure is an estimate, never a measurement."""
    return max(1, round(len(prompt) / 4))


def expected_cost(provider: str, model: str, loop_class: str,
                  est_input_tokens: int, rates: dict,
                  cached_prefix_tokens: int = 0) -> dict:
    """The expected-cost figure for one candidate, with its basis."""
    price_in, price_out, _ = pricing_mod.price_info(provider, model)
    cap = lanes_mod.cap_for(model)
    cached_rate = CACHED_INPUT_RATES.get(model)
    cache_adjusted = bool(cached_rate is not None and cached_prefix_tokens > 0)
    if cache_adjusted:
        live_in = (cached_prefix_tokens * cached_rate
                   + max(0, est_input_tokens - cached_prefix_tokens)
                   * price_in) / max(1, est_input_tokens)
    else:
        live_in = price_in
    raw = (est_input_tokens * live_in + cap * price_out) / 1_000_000.0
    rate = measured_rate(rates, model, loop_class)
    if rate is None:
        return {"model": model, "expected_cost_usd": round(raw, 6),
                "rate_basis": "EXPECTED", "success_rate": None,
                "cache_adjusted": cache_adjusted,
                "contract_cap_tokens": cap}
    if rate <= 0:
        return {"model": model, "expected_cost_usd": None,
                "rate_basis": "MEASURED", "success_rate": 0.0,
                "cache_adjusted": cache_adjusted,
                "contract_cap_tokens": cap,
                "note": "measured success rate is zero on this class"}
    return {"model": model,
            "expected_cost_usd": round(raw / rate, 6),
            "rate_basis": "MEASURED", "success_rate": rate,
            "cache_adjusted": cache_adjusted,
            "contract_cap_tokens": cap}


def rank_candidates(loop_class: str, prompt: str, rates: dict,
                    pool_state: dict | None = None) -> list[dict]:
    """Rank the class's chain candidates by expected cost per
    successful loop. Free-pool seats price at $0 while the pool has
    headroom; near exhaustion they carry the cheapest paid figure as
    shadow price (opportunity cost). Quality floors and containment
    are upstream of this ranking — it orders eligible seats only."""
    chain = list(throttle_mod.COMMODITY_CHAIN)
    est_in = estimate_input_tokens(prompt)
    pool = pool_state or {}
    pool_exhausted = (pool.get("free_used_est", 0)
                      >= 0.9 * pool.get("free_limit", POOL_FREE_LIMIT))
    ranked = []
    for model in chain:
        rule = throttle_mod.MODELS.get(model)
        if rule is None:
            continue
        entry = expected_cost(rule.provider, model, loop_class,
                              est_in, rates)
        entry["provider"] = rule.provider
        ranked.append(entry)
    paid = [e["expected_cost_usd"] for e in ranked
            if e["expected_cost_usd"]]
    cheapest_paid = min(paid) if paid else None
    for entry in ranked:
        if entry["provider"] == "openrouter" and pool_exhausted \
                and cheapest_paid is not None:
            entry["shadow_price_usd"] = cheapest_paid
            entry["expected_cost_usd"] = cheapest_paid
            entry["pool_state"] = "near-exhaustion — shadow priced"
    ranked.sort(key=lambda e: (e["expected_cost_usd"] is None,
                               e["expected_cost_usd"] or 0.0))
    return ranked


def build_stamp(provider: str, model: str, loop_class: str, prompt: str,
                rates: dict, pool_state: dict | None = None,
                cached_prefix_tokens: int = 0) -> dict:
    """The run-record stamp for the fired model. Any failure in the
    live computation produces the PRICING_STALE fallback stamp — the
    resolve proceeds on the static mapping and the stamp says so."""
    try:
        entry = expected_cost(provider, model, loop_class,
                              estimate_input_tokens(prompt), rates,
                              cached_prefix_tokens)
        pool = pool_state or {}
        return {
            "expected_cost_usd": entry["expected_cost_usd"],
            "rate_basis": entry["rate_basis"],
            "success_rate": entry["success_rate"],
            "cache_adjusted": entry["cache_adjusted"],
            "price_table_version": pricing_mod.PRICE_TABLE_VERSION,
            "pool_state": pool.get("state", "unknown"),
            "lambda": 1.0,
            "lambda_state": "neutral-unratified",
            # Treasury grade flag (2026-11-12): burn fractions derive
            # from metered ticket sums until the Nov 22 reconciliation
            # re-bases them on cash actuals — grade EXPECTED until
            # then. Any lambda-influenced resolve carries the grade
            # of its input on the ticket.
            "lambda_input_grade": "EXPECTED",
            "lambda_input_basis": "burn fractions from metered ticket "
                                  "sums; re-based on reconciled cash "
                                  "actuals at the Nov 22 reconciliation",
            "pricing_stale": False,
        }
    except Exception as exc:  # failure posture: fall back + stamp
        return {
            "expected_cost_usd": None,
            "rate_basis": None, "success_rate": None,
            "cache_adjusted": False,
            "price_table_version": pricing_mod.PRICE_TABLE_VERSION,
            "pool_state": "unknown", "lambda": 1.0,
            "lambda_state": "neutral-unratified",
            "lambda_input_grade": "EXPECTED",
            "lambda_input_basis": "burn fractions from metered ticket "
                                  "sums; re-based on reconciled cash "
                                  "actuals at the Nov 22 reconciliation",
            "pricing_stale": True,
            "stale_cause": f"{type(exc).__name__}: {exc}"[:120],
        }
