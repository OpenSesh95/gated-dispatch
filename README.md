# gated-dispatch

**Dispatch → verify → approval gate → ledger.** A small, runnable reference implementation of an approval-gated LLM dispatch pipeline: every model call is checked by deterministic verification, stops at a human approval gate, and is metered into a cost ledger — including the failures.

Extracted from a private working system and published as a clean, self-contained slice. No dependencies beyond the Python standard library.

## Why

Agentic tooling usually demos the happy path. Operating a system looks different: calls fail checks, reviewers reject output, providers go down — and every one of those events has a cost and a record. This slice implements the control loop around the model call, which is where the operating discipline actually lives:

- **Verification before review.** Deterministic checks (non-empty, size bounds, required terms, optional JSON validity) run before a human ever sees the output. A failed check is rejected automatically and never reaches the gate.
- **A gate that stays closed.** Nothing is "approved" by default. Non-interactive runs must opt in explicitly; an unattended run without that opt-in records a gate rejection, not a pass.
- **A ledger that keeps the failures.** Exactly one JSONL row per run — approved, rejected at verification, rejected at the gate, or provider error — with token counts and an estimated cost from a published list-price table.
- **Privacy by construction.** Ledger rows store the prompt's SHA-256 and length, never the raw prompt, so the ledger can be shared as an operating receipt.

## Quickstart

```bash
# offline: run the test suite (stub transport, no API key needed)
python -m unittest discover -s tests -v

# live: point at any OpenAI-compatible endpoint
export GATED_DISPATCH_BASE_URL="https://api.openai.com/v1"
export GATED_DISPATCH_API_KEY="..."   # read from the environment only; never stored
gated-dispatch "Summarize this week's change log in two sentences." \
  --model gpt-5-mini --require-term "change" --ledger ledger.jsonl
```

Without a console entry point: `python -m gated_dispatch.cli "…"` after `pip install -e .`, or call `gated_dispatch.cli.run(...)` from your own code with an injected transport.

## The pipeline

```
prompt ──► dispatch ──► verify ──► approval gate ──► ledger (approved)
              │            │             │
              │            └─ fail ──────┴──► ledger (rejected-verification)
              ├─ error ─────────────────────► ledger (error)
              └─ gate closed / rejected ────► ledger (rejected-gate)
```

## Ledger format

One JSON object per line:

```json
{"ticket": "GD-20261110-0001", "ts": "2026-11-10T20:14:03+00:00", "model": "gpt-5-mini", "prompt_sha256": "…", "prompt_chars": 41, "tokens_in": 120, "tokens_out": 45, "cost_usd": 0.00012, "status": "approved", "checks": {"non_empty": true, "within_max_chars": true, "contains:change": true}}
```

Costs are estimates from list prices (`gated_dispatch/pricing.py`, November 2026) — a model with no listed price stops the run rather than dispatching unmetered.

## Layout

- `gated_dispatch/provider.py` — one chat completion over an OpenAI-compatible HTTP API; injectable transport for testing
- `gated_dispatch/verify.py` — the deterministic check set
- `gated_dispatch/gate.py` — the human approval gate
- `gated_dispatch/ledger.py` — JSONL ledger with ticket ids and cost metering
- `gated_dispatch/cli.py` — the pipeline wiring and command-line entry point
- `tests/test_slice.py` — the full loop, tested offline: approval, both rejection paths, and provider error

## Status

v0.1.0 — the slice runs end to end. Architecture decision records and diagrams live under `docs/`; operating receipts (aggregate cost per ticket, failure log) are published from real runs, not staged for the README.
