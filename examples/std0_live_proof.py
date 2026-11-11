"""STD-0 live proof: one real dispatch round-trip per live lane.

Runs the full pipeline (preflight -> dispatch via the operator's
connector helpers, which hold the keys -> verification -> approval
gate -> metered ticket) once per lane and prints the tickets. The
gate is answered by a scripted "y" so the run is reproducible; gate
timestamps and owner-minutes on the tickets are real.

Usage: python examples/std0_live_proof.py <ledger-path>
"""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from gated_dispatch import cli  # noqa: E402

LANES = [
    ("anthropic", "claude-haiku-5-5"),
    ("google", "gemini-3.8-flash"),
    ("xai", "grok-4.20-0309-non-reasoning"),
]

PROMPT = "Reply with exactly: lane live"


def main() -> int:
    ledger = sys.argv[1] if len(sys.argv) > 1 else "std0-proof-ledger.jsonl"
    for provider, model in LANES:
        row = cli.run(
            PROMPT,
            model,
            ledger_path=ledger,
            provider=provider,
            envelope="frontier",
            required_terms=("lane live",),
            auto_approve=False,
            input_fn=lambda prompt="": "y",
        )
        print(
            f"{row['ticket']} {provider}/{row['model_served']} "
            f"in={row['tokens_in']} out={row['tokens_out']} "
            f"cost=${row['cost_usd']:.6f} status={row['status']} "
            f"match={row['model_match']} owner_min={row['owner_minutes']}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
