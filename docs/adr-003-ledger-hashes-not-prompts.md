# ADR-003: The ledger stores prompt hashes, never raw prompts

**Status:** Accepted · 2026-11-10

## Context

The ledger exists to be shared — as an operating receipt, in a README, in a review. Prompts can contain anything: client context, personal data, material that was never meant to leave the machine. A log that cannot be published will, in practice, never be audited.

## Decision

Each ledger row stores the prompt's SHA-256 and character count, plus model, token usage, estimated cost, verification checks, and outcome status. Raw prompts and completions are never written to the ledger.

## Alternatives rejected

- **Full prompt/response logging** — maximally debuggable and permanently unpublishable; every share becomes a redaction project, so sharing stops happening.
- **No ledger (console output only)** — no operating history at all; cost and failure rates become impressions instead of numbers.
- **Encrypted prompt column** — keeps the liability and adds key management; the receipt still cannot be shown to anyone without a decryption ceremony.

## Consequences

Any row can be shown to anyone. The trade is real: a specific run cannot be replayed from the ledger alone. That is accepted — reproducibility of *cost and outcome* matters more here than reproducibility of *content*, and a hash still proves which prompt a row belongs to when the prompt is supplied separately.
