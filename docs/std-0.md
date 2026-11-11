# STD-0 — Metered Dispatch

**Status:** Live · v0.2.0 · 2026-11-11

STD-0 is the metering standard every dispatch in this system runs under: **no dispatch happens without a complete ticket, and no ticket is computed from estimates.**

## The ticket

One ledger row per run, written whatever the outcome. Fields:

| Field | Source |
|---|---|
| `provider`, `lane` | the dispatch's lane (anthropic / google / xai / open) |
| `model`, `model_served`, `model_match` | requested vs actually served — alias drift is flagged, never hidden |
| `tokens_in`, `tokens_out` | the API response's own usage fields (`tokens_source: api_usage`) |
| `cost_usd` | actual tokens × published list price (`gated_dispatch/pricing.py`, sourced and dated per entry) |
| `envelope`, `envelope_mtd_usd`, `lane_mtd_usd`, `backstop_mtd_usd` | the budget envelope drawn from, with month-to-date snapshots read at write time |
| `owner_minutes`, `owner_minute_usd` | gate shown→decision elapsed (clamped), valued at the interim $2.00/owner-minute rate |
| `status` | approved · rejected-verification · rejected-gate · hold-90 · blocked-envelope · blocked-unmetered · error |

## Rules

1. **Unmetered stops the run.** A model with no published price in the table stops the dispatch before any provider call (`blocked-unmetered`). A served model with no price is an error row, never a silent estimate.
2. **Envelopes hard-stop at 100%.** Envelope caps (monthly): frontier $121.33 · sweeps $10.92 · open-weight $15.00 · health $7.75 · CI/local metered, uncapped until a baseline exists. Lane sub-ceilings cut across envelopes: Claude $75 · Gemini $35 · Grok $30 · Open $15. A $155 aggregate backstop stops all non-gated dispatch.
3. **The 90% hold.** At 90% of any envelope, lane ceiling, or the backstop, work holds for the owner's word; an acknowledged hold proceeds and the acknowledgement is recorded.
4. **Unclassed dispatches are refused.** The envelope is a required field on every run.
5. **Owner-minutes are metered passively** at the approval gate — shown and decision timestamps, elapsed time clamped (provisional 5-minute ceiling, to be set from the first metered weeks' distribution). No self-report, no timesheets.

## Why actuals, not estimates

A prior commission measured a ±50% error band on estimated pricing. An envelope regime built on estimates cannot tell a real anomaly from a rounding error, so STD-0 computes every ticket from the usage fields the provider actually returned, multiplied by a published, dated rate. Where a rate is genuinely unsourced (the open-weight lane, pending verification), the lane stays unpriced and its dispatches stop — a visible gap, not a quiet guess.

## Proof

See `std-0-proof.md`: one real dispatch round-trip per live lane, ticketed end to end.
