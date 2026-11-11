# Changelog

**v0.2.0** — STD-0 Metered Dispatch: lane adapters for Anthropic, Gemini, and xAI with token counts parsed from each API's usage fields; complete tickets (provider, requested/served model with drift flagging, envelope + lane month-to-date snapshots, owner-minute accounting at the interim $2.00 rate); budget envelopes with lane sub-ceilings, the 90% hold, and hard stops; unmetered models stop before dispatch. Proven live with one ticketed round-trip per lane (docs/std-0-proof.md). 12 offline tests green.

**v0.1.0** — First slice: dispatch → verify → approval gate → ledger, standard library only, full loop covered by offline tests.
