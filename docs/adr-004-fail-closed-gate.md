# ADR-004: The approval gate fails closed

**Status:** Accepted · 2026-11-10

## Context

The gate is the control the whole design exists to demonstrate. Its failure mode matters more than its happy path: a gate that approves when nobody answered is not a gate.

## Decision

Approval requires an explicit human yes at the prompt. End-of-input, a non-interactive session, or any ambiguity records the run as `rejected-gate`. Automated runs may opt in with an explicit flag (`--yes`), which is itself a recorded, reviewable choice — there is no silent or default pass.

## Alternatives rejected

- **Default-approve with a timeout** — converts reviewer absence into approval; the ledger would show approvals nobody gave.
- **Async approval queue** (approve later from a dashboard) — a reasonable product feature, but it splits the run from its record and adds a service to operate; out of scope for the slice.
- **Post-hoc review** (ship now, review the log later) — appropriate for low-stakes generation, wrong for a reference implementation whose point is the gate.

## Consequences

Unattended runs stop rather than drift, which is occasionally inconvenient and always legible: every `approved` row in the ledger corresponds to a decision a person (or an explicit automation opt-in) actually made.
