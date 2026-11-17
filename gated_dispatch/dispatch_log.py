"""Dispatch-record instrumentation — the raw feed for Treasury's meter.

Agreed schema v1.1 (Treasury SLO-TABLE.md §5.1, closed 2026-11-12).
One record per dispatch ATTEMPT; attempts of one loop share loop_id
(the gate ticket id). Fields:

    loop_id, loop_class, seat, model, attempt_no,
    ts_dispatch, ts_outcome, latency,
    size_band, band_basis, tokens_in, tokens_out,
    cost_usd, cost_source, outcome,
    form_gate_pass, trace_fidelity,
    owner_surface_ts, owner_tap_ts,
    run_outcome, degraded_from,
    question_key, question_shingles

loop_class is the SLO axis only (panel · commission · junior ·
ruling · defect · lower-order); throttle behavior is gate-internal.
size_band names the token ladder: mechanical <=25k, execution
<=60k, reasoning <=120k, L4 above; band_basis marks bands computed
from a prompt estimate (loops that never fired, attempt_no 0).
outcome is per attempt: success | fail | partial (partial = the
call returned but the loop did not approve). run_outcome, form_gate
and the owner timestamps ride the FINAL attempt record only; trace
fidelity is null at this layer (UNMEASURED — sampler-owned).

Retrieval-before-generation (standing rule, 2026-11-12): the record
carries question_key (SHA-256 of the question, the same hash the
ticket stores) and question_shingles (hashes of normalized word
3-grams, capped) — hashes only, never raw text. summarize() computes
the repeat-question rate per loop class from them: a loop counts as
a repeat when its question matches an earlier loop that ended in
success (exact key, or shingle Jaccard >= threshold).

The computed read (p50/p95 per loop class, rolling 7-day window)
lives in Treasury's meter layer; summarize() is the reference
implementation that proves the feed is consumable.
"""

import hashlib
import json
import os
import re
from datetime import datetime, timedelta, timezone

# Lab environments (C-026 R4 · D-BENCH-1 item 1): every attempt
# record carries one; prod is the default for unsteered traffic.
ENVS = ("dev", "test", "cert", "prod")

BANDS = [(25_000, "mechanical"), (60_000, "execution"), (120_000, "reasoning")]
SHINGLE_CAP = 32
REPEAT_JACCARD = 0.8


def size_band(total_tokens: int) -> str:
    for ceiling, label in BANDS:
        if total_tokens <= ceiling:
            return label
    return "L4"


def question_key(prompt: str) -> str:
    return hashlib.sha256(prompt.encode("utf-8")).hexdigest()


def question_shingles(prompt: str) -> list[str]:
    words = re.findall(r"[a-z0-9]+", prompt.lower())
    grams = {" ".join(words[i:i + 3]) for i in range(max(0, len(words) - 2))}
    if not grams and words:
        grams = {" ".join(words)}
    hashes = sorted(
        hashlib.sha256(g.encode("utf-8")).hexdigest()[:12] for g in grams
    )
    return hashes[:SHINGLE_CAP]


def append_record(path: str, **fields) -> dict:
    record = {
        "loop_id": fields["loop_id"],
        "loop_class": fields["loop_class"],
        "seat": fields["seat"],
        "model": fields["model"],
        "attempt_no": fields["attempt_no"],
        "ts_dispatch": fields["ts_dispatch"],
        "ts_outcome": fields["ts_outcome"],
        "latency": round(float(fields["latency"]), 3),
        "size_band": size_band(fields["total_tokens"]),
        "band_basis": fields.get("band_basis", "actual"),
        "tokens_in": int(fields.get("tokens_in", 0)),
        "tokens_out": int(fields.get("tokens_out", 0)),
        "cost_usd": round(float(fields.get("cost_usd", 0.0)), 6),
        "cost_source": fields.get("cost_source", "list"),
        "finish_reason": fields.get("finish_reason"),
        "outcome": fields["outcome"],
        "form_gate_pass": fields.get("form_gate_pass"),
        "trace_fidelity": None,
        "owner_surface_ts": fields.get("owner_surface_ts"),
        "owner_tap_ts": fields.get("owner_tap_ts"),
        "run_outcome": fields.get("run_outcome"),
        "degraded_from": fields.get("degraded_from"),
        "stall_cause": fields.get("stall_cause"),
        "hop_count": fields.get("hop_count"),
        "seat_confidence": fields.get("seat_confidence"),
        "seat_contribution": fields.get("seat_contribution"),
        "seat_mode": fields.get("seat_mode", "chain"),
        "env": fields.get("env", "prod"),
        "profile_version": fields.get("profile_version"),
        # C-039 / Treasury §5.11: the prompt stamp rides the feed —
        # prompt_id + version + decoding class feed-resident, the
        # content hash on the feed + pre-registration only (never the
        # WS-4 dataset). Null on records minted before the standard.
        "prompt_stamp": fields.get("prompt_stamp"),
        # C-047: the input manifest rides beside the prompt stamp
        # (interim in run records; feed-field adoption is Treasury's
        # §7 call, flagged with the C-047 tasking).
        "input_manifest": fields.get("input_manifest"),
        "assembly_pattern": fields.get("assembly_pattern"),
        # C-042: the live-cost stamp (expected cost + rate basis +
        # price-table version + pool state + lambda state, or the
        # PRICING_STALE fallback shape). Null pre-resolution.
        "live_cost": fields.get("live_cost"),
        # Query Routing Table v0 (deployed 2026-11-15): the routing
        # stamp on the final record of a routed run (table version +
        # hash + class + position). Null on unrouted runs.
        "routing": fields.get("routing"),
        # PII masking (Increment 2 wiring, 2026-11-17): counts by
        # class only — never values (the vault map never leaves the
        # gate host). Null on unmasked runs.
        "masking": fields.get("masking"),
        # Grant-first booking (2026-11-17): the booking stamp on the
        # final record of a grant-covered run (remaining before the
        # ticket + the straddle flag). Null on cash-booked runs.
        "grant": fields.get("grant"),
        "contract": fields.get("contract"),
        "queue_wait": fields.get("queue_wait"),
        "verify_ms": fields.get("verify_ms"),
        "verify_cost_usd": fields.get("verify_cost_usd"),
        "question_key": fields.get("question_key"),
        "question_shingles": fields.get("question_shingles", []),
    }
    with open(path, "a", encoding="utf-8") as fh:
        fh.write(json.dumps(record, sort_keys=True) + "\n")
    return record


def _percentile(values: list[float], pct: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    idx = min(len(ordered) - 1, int(round((pct / 100.0) * (len(ordered) - 1))))
    return ordered[idx]


def _jaccard(a: set, b: set) -> float:
    if not a or not b:
        return 0.0
    return len(a & b) / len(a | b)


SUCCESS_RUN_OUTCOMES = {"approved", "success"}


FUZZY_MIN_SHINGLES = 8  # schema v1.2 small-set floor (Treasury ruling)


def summarize(path: str, now: datetime | None = None, window_days: int = 7,
              throttle_state_path: str | None = None) -> dict:
    """Per loop class: attempts, loops, p50/p95 latency, outcomes,
    and the repeat-question rates (rolling window).

    Schema v1.2 (Treasury SLO-TABLE §5.2): the rates are STRATIFIED
    — exact-key matches and fuzzy (shingle Jaccard >= 0.8) matches
    publish side by side, never blended. Fuzzy matching applies
    only when both loops carry >= 8 shingles (small-set floor).
    The counted loops sit inside the window, but the match search
    reaches back over ALL retained records: a question answered
    three weeks ago is still answered. A repeat requires the
    earlier loop to have ended in success; a re-ask after a failed
    loop is a retry, not a repeat. Report-only in v1 — no target.
    """
    now = now or datetime.now(timezone.utc)
    cutoff = now - timedelta(days=window_days)
    attempts: dict[str, list] = {}
    loops: dict[str, dict] = {}  # loop_id -> aggregate, in file order
    if os.path.exists(path):
        with open(path, encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                rec = json.loads(line)
                ts = datetime.fromisoformat(rec["ts_outcome"])
                loop = loops.setdefault(rec["loop_id"], {
                    "loop_class": rec["loop_class"],
                    "question_key": rec.get("question_key"),
                    "shingles": set(rec.get("question_shingles", [])),
                    "run_outcome": None,
                    "last_ts": ts,
                })
                loop["last_ts"] = max(loop["last_ts"], ts)
                if rec.get("run_outcome") is not None:
                    loop["run_outcome"] = rec["run_outcome"]
                if ts >= cutoff:
                    attempts.setdefault(rec["loop_class"], []).append(rec)
    # Stability view (operator-study measure 1): per-model
    # reliability from the same windowed attempt records —
    # outcome shares and mean latency. Report-only in v1.
    by_model: dict[str, list] = {}
    for recs in attempts.values():
        for r in recs:
            if r.get("attempt_no", 0) >= 1:
                by_model.setdefault(r["model"], []).append(r)
    stability: dict[str, dict] = {}
    for mdl, recs in sorted(by_model.items()):
        n = len(recs)
        counts: dict[str, int] = {}
        for r in recs:
            counts[r["outcome"]] = counts.get(r["outcome"], 0) + 1
        stability[mdl] = {
            "attempts": n,
            "success_share": round(counts.get("success", 0) / n, 3),
            "fail_share": round(counts.get("fail", 0) / n, 3),
            "superseded_share": round(counts.get("superseded", 0) / n, 3),
            "mean_latency": round(sum(float(r["latency"]) for r in recs) / n, 3),
        }
    if throttle_state_path and os.path.exists(throttle_state_path):
        try:
            with open(throttle_state_path, encoding="utf-8") as fh:
                tstate = json.load(fh)
            for mdl, view in stability.items():
                view["breach_count"] = int(
                    tstate.get(mdl, {}).get("breach_count", 0)
                )
        except (OSError, ValueError):
            pass
    out: dict[str, dict] = {"_stability": stability}
    for cls, recs in sorted(attempts.items()):
        lat = [float(r["latency"]) for r in recs]
        outcomes: dict[str, int] = {}
        for r in recs:
            outcomes[r["outcome"]] = outcomes.get(r["outcome"], 0) + 1
        # Treasury computation rules (§5.7): seat-field means publish
        # with their non-null coverage share beside them (a mean over
        # silent callers is a subset claim), and cost per successful
        # loop publishes as dispatch cost and all-in cost side by
        # side (all-in = dispatch + verifier overhead).
        finals = [r for r in recs if r.get("run_outcome") is not None]
        succ_loops = len({r["loop_id"] for r in finals if r["run_outcome"] == "approved"})

        def _mean_cov(field):
            vals = [r[field] for r in finals if r.get(field) is not None]
            if not finals:
                return None, 0.0
            mean = round(sum(vals) / len(vals), 3) if vals else None
            return mean, round(len(vals) / len(finals), 3)

        conf_mean, conf_cov = _mean_cov("seat_confidence")
        contrib_mean, contrib_cov = _mean_cov("seat_contribution")
        entry = {
            "attempts": len(recs),
            "p50": round(_percentile(lat, 50), 3),
            "p95": round(_percentile(lat, 95), 3),
            "outcomes": outcomes,
            "seat_confidence_mean": conf_mean,
            "seat_confidence_coverage": conf_cov,
            "seat_contribution_mean": contrib_mean,
            "seat_contribution_coverage": contrib_cov,
        }
        if succ_loops:
            dispatch_total = sum(float(r.get("cost_usd") or 0.0) for r in recs)
            verify_total = sum(float(r.get("verify_cost_usd") or 0.0) for r in finals)
            entry["cost_per_successful_loop"] = round(dispatch_total / succ_loops, 6)
            entry["all_in_cost_per_successful_loop"] = round(
                (dispatch_total + verify_total) / succ_loops, 6
            )
        out[cls] = entry
    # Repeat strata per class over window loops, priors from all
    # retained records (ordered by loop close time).
    ordered = sorted(loops.values(), key=lambda l: l["last_ts"])
    seen: dict[str, list] = {}
    totals: dict[str, int] = {}
    exact: dict[str, int] = {}
    fuzzy: dict[str, int] = {}
    for loop in ordered:
        cls = loop["loop_class"]
        prior = seen.setdefault(cls, [])
        if loop["last_ts"] >= cutoff:
            totals[cls] = totals.get(cls, 0) + 1
            if any(loop["question_key"] and loop["question_key"] == p["question_key"]
                   for p in prior):
                exact[cls] = exact.get(cls, 0) + 1
            elif (len(loop["shingles"]) >= FUZZY_MIN_SHINGLES and any(
                    len(p["shingles"]) >= FUZZY_MIN_SHINGLES
                    and _jaccard(loop["shingles"], p["shingles"]) >= REPEAT_JACCARD
                    for p in prior)):
                fuzzy[cls] = fuzzy.get(cls, 0) + 1
        if loop["run_outcome"] in SUCCESS_RUN_OUTCOMES:
            prior.append(loop)
    for cls, total in totals.items():
        entry = out.setdefault(cls, {"attempts": 0, "p50": 0.0, "p95": 0.0, "outcomes": {}})
        e, f = exact.get(cls, 0), fuzzy.get(cls, 0)
        entry["loops"] = total
        entry["repeat_exact_loops"] = e
        entry["repeat_fuzzy_loops"] = f
        entry["repeat_exact_rate"] = round(e / total, 4) if total else 0.0
        entry["repeat_fuzzy_rate"] = round(f / total, 4) if total else 0.0
        entry["repeat_loops"] = e + f
        entry["repeat_question_rate"] = round((e + f) / total, 4) if total else 0.0
    return out
