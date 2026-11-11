"""Pipeline: dispatch -> verify -> approval gate -> ledger.

Every run writes exactly one ledger row, including failures — the
ledger is the operating history, not a highlight reel.
"""

import argparse
import sys

from . import gate as gate_mod
from . import ledger as ledger_mod
from . import provider, verify as verify_mod


def run(
    prompt: str,
    model: str,
    ledger_path: str = "ledger.jsonl",
    required_terms=(),
    expect_json: bool = False,
    auto_approve: bool = False,
    transport=None,
) -> dict:
    try:
        completion = provider.dispatch(prompt, model, transport=transport)
    except Exception as exc:  # provider failure is a ledger event too
        return ledger_mod.append_row(
            ledger_path,
            prompt=prompt,
            model=model,
            tokens_in=0,
            tokens_out=0,
            status=f"error:{type(exc).__name__}",
        )
    result = verify_mod.verify(
        completion.text, required_terms=required_terms, expect_json=expect_json
    )
    if not result.passed:
        return ledger_mod.append_row(
            ledger_path,
            prompt=prompt,
            model=completion.model,
            tokens_in=completion.tokens_in,
            tokens_out=completion.tokens_out,
            status="rejected-verification",
            checks=result.checks,
        )
    try:
        approved = gate_mod.approve(completion.text, auto_approve=auto_approve)
    except gate_mod.GateRejected:
        approved = False
    return ledger_mod.append_row(
        ledger_path,
        prompt=prompt,
        model=completion.model,
        tokens_in=completion.tokens_in,
        tokens_out=completion.tokens_out,
        status="approved" if approved else "rejected-gate",
        checks=result.checks,
    )


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        prog="gated-dispatch",
        description="Dispatch one prompt through verification and an approval gate, metered into a cost ledger.",
    )
    parser.add_argument("prompt", help="the prompt to dispatch")
    parser.add_argument("--model", default="gpt-5-mini")
    parser.add_argument("--ledger", default="ledger.jsonl")
    parser.add_argument("--require-term", action="append", default=[])
    parser.add_argument("--expect-json", action="store_true")
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
        required_terms=args.require_term,
        expect_json=args.expect_json,
        auto_approve=args.yes,
    )
    print(f"{row['ticket']}  {row['status']}  ${row['cost_usd']:.6f}  -> {args.ledger}")
    return 0 if row["status"] == "approved" else 1


if __name__ == "__main__":
    sys.exit(main())
