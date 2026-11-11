# ADR-002: Deterministic verification runs before human review

**Status:** Accepted · 2026-11-10

## Context

Human review is the scarcest resource in the pipeline. Model output that is empty, oversized, missing required content, or malformed should never consume a reviewer's attention — and a reviewer should never be the first line of defense against defects a machine can catch.

## Decision

Every completion passes a deterministic check set first — non-empty, size bound, required terms, optional JSON validity. Only verified output reaches the approval gate. Verification failures are rejected automatically and recorded in the ledger with the failing checks named.

## Alternatives rejected

- **Review-first (human sees everything)** — does not scale, and trains reviewers to rubber-stamp whatever usually passes.
- **Model-as-judge as the gate** — a second model call doubles cost per dispatch and replaces a checkable rule with an opinion; useful as an advisory signal, not as the control.
- **Verification after approval** — inverts the economics: the expensive resource (attention) is spent before the cheap one (rules).

## Consequences

The gate sees only plausible output, reviewer attention stays expensive on purpose, and the ledger's verification-rejection rows make model quality measurable over time instead of anecdotal.
