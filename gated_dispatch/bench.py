"""Loop-grain benchmark summary records (D-BENCH-1 item 3).

The meter layer's record: one summary per completed loop,
derived from the gate's per-attempt feed. The gate's per-attempt
contract is untouched; this module only reads it.

Fields per C-027 §2.1: wall_ms (first ts_dispatch -> final
ts_outcome) · service_ms (sum of attempt latencies; a hedged
loop reads the winning attempt's latency, §5.6) · queue_ms
(owner_tap - owner_surface where both exist) with transit
printed only when every component exists · the §2.2/§2.3 VALUE
fields · gear · §3's public-mapping fields (caller-supplied,
never fabricated).

decision_ready defaults by rule: a stopped loop is FALSE judged
by the gate record; an unscored production loop is PENDING
judged by the follow-up record. Scored runs pass their judge's
verdict in — a record with no named judge is invalid, so the
defaults always name one.
"""

from __future__ import annotations

import json
from datetime import datetime

from . import calibration as calibration_mod
from . import inputs as inputs_mod
from . import prompts as prompts_mod

GEARS = ("blade", "bow", "arrows", "accessories", "armor")
JUDGES = ("gate-scorer", "trial-scorer", "mechanical-scorer",
          "follow-up-record", "gate-record")


def _ms(ts_a: str | None, ts_b: str | None) -> float | None:
    if not ts_a or not ts_b:
        return None
    try:
        a = datetime.fromisoformat(ts_a.replace("Z", "+00:00"))
        b = datetime.fromisoformat(ts_b.replace("Z", "+00:00"))
    except ValueError:
        return None
    return round((b - a).total_seconds() * 1000, 1)


def summarize_loop(attempts: list[dict], *, judged: dict | None = None,
                   gear: str | None = None,
                   credit_draw_usd: float | None = None,
                   public_analog: str | None = None,
                   public_score=None, measured_score=None,
                   suite_version: str | None = None,
                   task_set_hash: str | None = None,
                   seed=None, leg_cert: str | None = None,
                   prompt_stamp: dict | None = None,
                   input_manifest: dict | None = None,
                   calibrations_path: str | None = None) -> dict:
    """Build the loop-grain summary from one loop's feed records."""
    if not attempts:
        raise ValueError("a summary needs at least one attempt record")
    if gear is not None and gear not in GEARS:
        raise ValueError(f"unknown gear {gear!r}")
    ordered = sorted(attempts, key=lambda r: r.get("attempt_no", 0))
    final = next((r for r in reversed(ordered)
                  if r.get("run_outcome") is not None), ordered[-1])
    stopped = any(r.get("attempt_no") == 0 for r in ordered)
    wall_ms = _ms(ordered[0].get("ts_dispatch"), final.get("ts_outcome"))
    hedged = any(r.get("outcome") == "superseded" for r in ordered)
    if hedged:
        service_ms = round(float(final.get("latency", 0.0)) * 1000, 1)
    else:
        service_ms = round(
            sum(float(r.get("latency", 0.0)) for r in ordered) * 1000, 1)
    queue_ms = _ms(final.get("owner_surface_ts"), final.get("owner_tap_ts"))
    transit_ms = None
    if wall_ms is not None and queue_ms is not None:
        transit_ms = round(wall_ms - service_ms - queue_ms, 1)
    owner_minutes = (round(queue_ms / 60000.0, 4)
                     if queue_ms is not None else None)
    cost_usd = round(sum(float(r.get("cost_usd", 0.0))
                         for r in ordered), 6)
    cost_source = final.get("cost_source")
    # VALUE (§2.2): judge + verdict
    judge_calibration = None
    if judged is not None:
        decision_ready = judged["decision_ready"]
        judged_by = judged["judged_by"]
        if judged_by not in JUDGES:
            raise ValueError(f"unknown judge {judged_by!r}")
        if decision_ready not in ("TRUE", "FALSE", "PENDING"):
            raise ValueError(f"bad decision_ready {decision_ready!r}")
        # C-041 R1: the judge's calibration state rides the summary.
        # A stood-down judge voids the score to provisional on the
        # spot (C-029 Group D judge rule).
        if calibrations_path:
            instrument = judged.get("judge_instrument") or judged_by
            judge_calibration = calibration_mod.check(
                calibrations_path, instrument)
        else:
            judge_calibration = {
                "status": "UNCALIBRATED",
                "reason": "no calibration store consulted for this score"}
        if judge_calibration.get("status") == "stood-down":
            decision_ready = "PENDING"
            judge_calibration = dict(
                judge_calibration,
                scores_voided="scores voided to provisional — "
                              "judge stood down")
    elif stopped:
        decision_ready, judged_by = "FALSE", "gate-record"
    else:
        decision_ready, judged_by = "PENDING", "follow-up-record"
    ready = 1 if decision_ready == "TRUE" else 0
    # value_per_usd (§2.3)
    basis = None
    if cost_source in ("ticks", "list", "free-tier"):
        basis = "metered"
        value_per_usd = (round(ready / cost_usd, 4) if cost_usd > 0
                         else "NO-DENOMINATOR")
    elif cost_source == "grant-offset":
        basis = "credit-draw"
        value_per_usd = (round(ready / credit_draw_usd, 4)
                         if credit_draw_usd else None)
    elif cost_source == "local-zero":
        basis = "local-zero"
        value_per_usd = "LOCAL-ZERO"
    else:
        value_per_usd = None
    # value_per_owner_minute (§2.3)
    if owner_minutes is None:
        value_per_owner_minute = "UNMEASURED"
    elif decision_ready == "PENDING":
        value_per_owner_minute = None
    else:
        value_per_owner_minute = (round(ready / owner_minutes, 4)
                                  if owner_minutes > 0 else "NO-DENOMINATOR")
    return {
        "record": "bench-summary",
        # D-BENCH-2 stamp lineage (H-C3): a score whose lineage
        # cannot re-derive its task set is unmeasured — it stays
        # on the record as evidence and steers nothing.
        "suite_version": suite_version,
        "task_set_hash": task_set_hash,
        "seed": seed,
        "leg_cert": leg_cert,
        # C-039: the prompt stamp cites from the bench summary until
        # Treasury adopts it as feed fields (§7 pattern). A scored run
        # without a complete stamp reads UNMEASURED (run_validity).
        "prompt_stamp": prompt_stamp,
        "run_validity": prompts_mod.run_validity(
            prompt_stamp, scored=judged is not None),
        # C-047: the input manifest + the reproducibility line — a
        # run is REPRODUCIBLE only when both stamps are complete.
        "input_manifest": input_manifest,
        "reproducibility": inputs_mod.reproducibility(
            prompt_stamp, input_manifest),
        "judge_calibration": judge_calibration,
        "loop_id": final.get("loop_id"),
        "loop_class": final.get("loop_class"),
        "seat": final.get("seat"),
        "model": final.get("model"),
        "size_band": final.get("size_band"),
        # §5.10 rule 1: a missing env reads as pre-delta — no
        # reader asserts prod on a pre-delta record.
        "env": final.get("env") or "pre-delta",
        "seat_mode": final.get("seat_mode", "chain"),
        "profile_version": final.get("profile_version"),
        "attempts": len(ordered),
        "tokens_in": sum(int(r.get("tokens_in", 0)) for r in ordered),
        "tokens_out": sum(int(r.get("tokens_out", 0)) for r in ordered),
        "cost_usd": cost_usd,
        "cost_source": cost_source,
        "degraded_from": final.get("degraded_from"),
        "stall_cause": final.get("stall_cause"),
        "finish_reason": final.get("finish_reason"),
        "truncated": final.get("finish_reason") == "MAX_TOKENS",
        "form_gate_pass": final.get("form_gate_pass"),
        "trace_fidelity": final.get("trace_fidelity"),
        "hop_count": final.get("hop_count"),
        "queue_wait": final.get("queue_wait"),
        "verify_ms": final.get("verify_ms"),
        "verify_cost_usd": final.get("verify_cost_usd"),
        "seat_confidence": final.get("seat_confidence"),
        "seat_contribution": final.get("seat_contribution"),
        "wall_ms": wall_ms,
        "service_ms": service_ms,
        "queue_ms": queue_ms,
        "transit_ms": transit_ms,
        "owner_minutes": owner_minutes,
        "gear": gear,
        "decision_ready": decision_ready,
        "judged_by": judged_by,
        "value_per_usd": value_per_usd,
        "value_basis": basis,
        "value_per_owner_minute": value_per_owner_minute,
        "public_analog": public_analog,
        "public_score": public_score,
        "measured_score": measured_score,
    }


def summarize_file(dispatch_path: str, out_path: str | None = None) -> list[dict]:
    """Summarize every loop in a dispatch feed; optionally append
    the summaries to out_path (default: <feed>.bench.jsonl)."""
    loops: dict[str, list[dict]] = {}
    with open(dispatch_path, encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if line:
                rec = json.loads(line)
                loops.setdefault(rec.get("loop_id"), []).append(rec)
    summaries = [summarize_loop(recs) for recs in loops.values()]
    target = out_path or (dispatch_path + ".bench.jsonl")
    with open(target, "a", encoding="utf-8") as fh:
        for summary in summaries:
            fh.write(json.dumps(summary, sort_keys=True) + "\n")
    return summaries


def main(argv=None) -> int:
    import argparse
    parser = argparse.ArgumentParser(prog="gated_dispatch.bench")
    parser.add_argument("dispatch_log")
    parser.add_argument("--out")
    args = parser.parse_args(argv)
    summaries = summarize_file(args.dispatch_log, args.out)
    for summary in summaries:
        print(json.dumps(summary, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())


# ------------------------------------------------------------- H-F
# Statistical discipline (C-029 Group F): every aggregated score
# claim carries n + a 95% interval (method named) + an
# INDETERMINATE flag when the interval spans its decision bar.
import math as _math


def _wilson(k: int, n: int, z: float = 1.96) -> tuple[float, float]:
    if n == 0:
        return (0.0, 0.0)
    p = k / n
    denom = 1 + z * z / n
    center = (p + z * z / (2 * n)) / denom
    half = (z * _math.sqrt(p * (1 - p) / n + z * z / (4 * n * n))) / denom
    return (round(max(0.0, center - half), 4),
            round(min(1.0, center + half), 4))


def rate_claim(values: list[bool], bar: float | None = None) -> dict:
    """A rate over boolean outcomes, with its 95% Wilson interval.
    Single-run scores print n=1 (their interval is honest about
    it). INDETERMINATE rides beside the point value when the
    interval spans the decision bar."""
    n = len(values)
    k = sum(1 for v in values if v)
    lo, hi = _wilson(k, n)
    return {
        "n": n, "rate": round(k / n, 4) if n else None,
        "ci95": [lo, hi] if n else None,
        "method": "Wilson score interval, 95%",
        "indeterminate": (bar is not None and n > 0
                          and lo <= bar <= hi),
    }


def mean_claim(values: list[float], bar: float | None = None) -> dict:
    """A mean with a normal-approximation 95% interval. n=1
    carries no interval — the claim prints its n and says so."""
    n = len(values)
    if n == 0:
        return {"n": 0, "mean": None, "ci95": None,
                "method": "normal approximation, 95%",
                "indeterminate": False}
    mean = sum(values) / n
    if n == 1:
        return {"n": 1, "mean": round(mean, 4), "ci95": None,
                "method": "normal approximation, 95% (n=1: no interval)",
                "indeterminate": bar is not None}
    var = sum((v - mean) ** 2 for v in values) / (n - 1)
    half = 1.96 * _math.sqrt(var / n)
    lo, hi = round(mean - half, 4), round(mean + half, 4)
    return {"n": n, "mean": round(mean, 4), "ci95": [lo, hi],
            "method": "normal approximation, 95%",
            "indeterminate": (bar is not None and lo <= bar <= hi)}
