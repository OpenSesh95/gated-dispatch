"""Pipeline (STD-0): preflight -> dispatch -> verify -> gate -> ticket.

Every run writes exactly one ledger row — a complete metered ticket —
including refusals, holds, verification and gate rejections, and
provider errors. An unpriced (unmetered) model stops the run before
any provider call is made.
"""

import argparse
import sys
import time
from datetime import datetime, timezone

from . import envelopes as envelopes_mod
from . import gate as gate_mod
from . import lanes
from . import ledger as ledger_mod
from . import verify as verify_mod
from .pricing import price_info

# Provisional clamp for owner-minute accounting (regime NEEDS-SOURCE
# NS-2): shown-to-decision latency above the ceiling counts as the
# ceiling, because latency is not attention. Set from the first two
# metered weeks' timestamp distribution; marked provisional until then.
OWNER_MINUTE_CLAMP = 5.0


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def run(
    prompt: str,
    model: str,
    ledger_path: str = "ledger.jsonl",
    provider: str = "openai",
    envelope: str = "frontier",
    required_terms=(),
    expect_json: bool = False,
    auto_approve: bool = False,
    acknowledge_hold: bool = False,
    transport=None,
    input_fn=input,
) -> dict:
    lane = lanes.LANE_OF_PROVIDER.get(provider, provider)
    base = dict(
        prompt=prompt,
        model=model,
        provider=provider,
        envelope=envelope,
        lane=lane,
    )

    # Unmetered dispatch stops the run (STD-0 / ADR-005).
    try:
        price_info(provider, model)
    except KeyError:
        snap = envelopes_mod.preflight(ledger_path, envelope, lane)
        return ledger_mod.append_row(
            ledger_path, tokens_in=0, tokens_out=0,
            status="blocked-unmetered", snapshot=snap, **base,
        )

    # Envelope + lane ceilings, read at write time (C-007 section 2).
    snap = envelopes_mod.preflight(ledger_path, envelope, lane)
    if snap["decision"] == "blocked":
        return ledger_mod.append_row(
            ledger_path, tokens_in=0, tokens_out=0,
            status=f"blocked-envelope:{snap['reason']}", snapshot=snap, **base,
        )
    if snap["decision"] == "hold" and not acknowledge_hold:
        return ledger_mod.append_row(
            ledger_path, tokens_in=0, tokens_out=0,
            status="hold-90", snapshot=snap, **base,
        )

    try:
        completion = lanes.dispatch(prompt, provider, model, transport=transport)
    except Exception as exc:  # provider failure is a ledger event too
        return ledger_mod.append_row(
            ledger_path, tokens_in=0, tokens_out=0,
            status=f"error:{type(exc).__name__}", snapshot=snap, **base,
        )

    # The served model must be priced too; alias drift is flagged on
    # the ticket via model_match, and an unpriced served model is an
    # error row, never a silent estimate.
    try:
        price_info(provider, completion.model_served)
    except KeyError:
        return ledger_mod.append_row(
            ledger_path,
            tokens_in=completion.tokens_in, tokens_out=completion.tokens_out,
            status="error:unmetered-served-model",
            model_served=completion.model_served, snapshot=snap, **base,
        )

    result = verify_mod.verify(
        completion.text, required_terms=required_terms, expect_json=expect_json
    )
    served = dict(model_served=completion.model_served, snapshot=snap)
    if not result.passed:
        return ledger_mod.append_row(
            ledger_path,
            tokens_in=completion.tokens_in, tokens_out=completion.tokens_out,
            status="rejected-verification", checks=result.checks, **served, **base,
        )

    shown_ts = _now()
    started = time.monotonic()
    try:
        approved = gate_mod.approve(
            completion.text, auto_approve=auto_approve, input_fn=input_fn
        )
    except gate_mod.GateRejected:
        approved = False
    decision_ts = _now()
    elapsed_min = (time.monotonic() - started) / 60.0
    owner_minutes = 0.0 if auto_approve else min(elapsed_min, OWNER_MINUTE_CLAMP)
    gate_info = {
        "shown": shown_ts,
        "decision": decision_ts,
        "auto": auto_approve,
        "clamp_min": OWNER_MINUTE_CLAMP,
    }
    return ledger_mod.append_row(
        ledger_path,
        tokens_in=completion.tokens_in, tokens_out=completion.tokens_out,
        status="approved" if approved else "rejected-gate",
        checks=result.checks, owner_minutes=owner_minutes, gate=gate_info,
        **served, **base,
    )


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        prog="gated-dispatch",
        description="Dispatch one prompt through verification and an approval gate, metered into a cost ledger (STD-0 ticket).",
    )
    parser.add_argument("prompt", help="the prompt to dispatch")
    parser.add_argument("--model", default="gpt-5-mini")
    parser.add_argument("--provider", default="openai",
                        help="anthropic | google | xai | openai | open")
    parser.add_argument("--envelope", default="frontier",
                        help="frontier | sweeps | open-weight | health | ci-local")
    parser.add_argument("--ledger", default="ledger.jsonl")
    parser.add_argument("--require-term", action="append", default=[])
    parser.add_argument("--expect-json", action="store_true")
    parser.add_argument("--acknowledge-hold", action="store_true",
                        help="proceed past a 90% hold on the owner's word (recorded)")
    parser.add_argument(
        "--yes",
        action="store_true",
        help="approve without prompting (for approved automation and tests)",
    )
    args = parser.parse_args(argv)
    row = run(
        args.prompt,
        args.model,
        ledger_path=args.ledger,
        provider=args.provider,
        envelope=args.envelope,
        required_terms=args.require_term,
        expect_json=args.expect_json,
        auto_approve=args.yes,
        acknowledge_hold=args.acknowledge_hold,
    )
    print(f"{row['ticket']}  {row['status']}  ${row['cost_usd']:.6f}  -> {args.ledger}")
    return 0 if row["status"] == "approved" else 1


if __name__ == "__main__":
    sys.exit(main())
