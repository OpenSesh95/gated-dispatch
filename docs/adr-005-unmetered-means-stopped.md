# ADR-005: Unmetered dispatches do not run

**Status:** Accepted · 2026-11-10

## Context

Cost discipline fails quietly: a new model gets used "just to try it," the price is never recorded, and the ledger develops gaps exactly where spending is least examined. Provider invoices arrive weeks later and cannot be reconciled per ticket.

## Decision

Cost is estimated at dispatch time from a versioned list-price table in the codebase (`gated_dispatch/pricing.py`). A model with no listed price raises an error and the dispatch does not run. Every ledger row — including failures — carries its estimated cost, so cost per ticket is computable the moment the run ends.

## Alternatives rejected

- **Provider billing as the only source** — accurate but late and aggregated; no per-ticket attribution, no same-day budget signal.
- **Estimates with a silent default price** — a wrong number presented as a measurement is worse than no number; gaps stay invisible.
- **Hard budget caps enforced in the slice** — real enforcement belongs to the operating system's budget process, which reads this ledger; the slice's job is to make the numbers exist and be trustworthy.

## Consequences

Adding a model is a deliberate, reviewed act (a row in the price table with a source and a date). Estimates can drift from invoiced amounts as providers reprice; the table is dated in the README so drift is visible rather than hidden.
