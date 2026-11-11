# ADR-006: Tickets are computed from API usage fields, never token estimates

**Status:** Accepted · 2026-11-11 (STD-0)

## Context

The budget regime (envelopes, lane sub-ceilings, a hard backstop) can only enforce what it can measure. A prior commission priced planned work from estimated token counts and landed within a ±50% error band — wide enough that an envelope "breach" could be pure estimation noise, and a real overrun could hide inside the band.

## Decision

Every ticket's token counts come from the provider API response's own usage fields, parsed per lane (Anthropic `usage.input/output_tokens`, Gemini `usageMetadata` with thinking tokens counted as billed output, OpenAI-shaped `usage.prompt/completion_tokens`). Cost is those actuals multiplied by a published, dated list price. A model with no published price does not dispatch; a served model that differs from the requested one is flagged on the ticket (`model_match: false`), never silently repriced or hidden.

## Alternatives rejected

- **Estimate tokens from prompt/response length** — reintroduces the ±50% band the standard exists to remove; character-to-token ratios vary by model and content.
- **Provider invoices as the system of record** — accurate but monthly and aggregated; no per-ticket attribution, no same-day envelope enforcement.
- **Trust the requested model id** — aliases drift; the served id in the response is the only defensible record of what ran.

## Consequences

Enforcement reads the same numbers billing will eventually show, per ticket, the moment a run ends. The cost: a pricing table that must be maintained with sources and dates, and lanes whose rates are unverified stay visibly unpriced — and stopped — until they are.
