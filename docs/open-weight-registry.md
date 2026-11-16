# Open-weight registry — disposition annotation

Amendment input (his directive 2026-11-12 19:38 CT, via PM).
Annotation only: no dispatch, no seating change. Every registry
id carries exactly 1 disposition: SEATED · SWARM (assembly
named) · BENCH (trial named) · QUARANTINE · RETIRED (cause
named).

Scope of this pass: the Jarvis inventory at the acting layer and
the GCP bench set. The 2 sets are the same 3 ids by design (the
GCP seat mirrors Jarvis). The GCP side has since CONVERTED (the
rows below carry the fire-order digests + connector proof
tickets). The Jarvis side stands STAGED: no /api/tags round-trip
has landed on Jarvis, so no Jarvis row can read SEATED — wiring
is not seating.

**Amendment 2026-11-13 (Package A W1-1, his tap 17:04 CT):** the
local-Ollama (Jarvis) lane reads **dev-loop nicety, never a
blocker**. Every production proof obligation and seat/registry
record that named the Jarvis lane re-points to the GCP lane
(gcp-ollama, VERIFIED). Nothing production waits on the Jarvis
lane; its trial completes if and when the lane round-trips, as a
dev-loop convenience, and blocks nothing either way.

## Rows

| id | family | disposition | trial / assembly |
|----|--------|-------------|------------------|
| qwen3:14b | Qwen | BENCH | Trial: bench proof — /api/tags round-trip + 1 STD-0-ticketed completion on the host (Track A Jarvis; Nightwatch GCP mirror). **Converted 2026-11-12 (fire-order return):** Nightwatch digest `bdbd181c33f2ed1b31c972991882db3cf4d192569092138a7d29e973cd9debe8` · size 9,276,198,565 B · pulled on gcp-ollama (us-central1-c); local completion HTTP 200 on the VM. Connector proof LANDED 2026-11-12: round-trip + ticket GD-20261113-0001 APPROVED through the connector (grant-offset, $0 cash). |
| deepseek-r1:14b | DeepSeek | BENCH | Trial: bench proof — same shape. **Converted 2026-11-12:** Nightwatch digest `c333b7232bdb521236694ffbb5f5a6b11cc45d98e9142c73123b670fca400b09` · size 8,988,112,209 B · pulled on gcp-ollama; local completion HTTP 200 on the VM. Connector proof LANDED 2026-11-12: ticket GD-20261113-0002 APPROVED through the connector. |
| llama3.1:8b | Meta | BENCH | Trial: bench proof — same shape. **Converted 2026-11-12:** Nightwatch digest `46e0c10c039e019119339687c3c1757cc81b9da49709a3b3924863ba87ca666e` · size 4,920,753,328 B · pulled on gcp-ollama; local completion HTTP 200 on the VM. Connector proof LANDED 2026-11-12: ticket GD-20261113-0003 APPROVED through the connector. |

## Rule 2 — small open weights (binds all 3 rows by name)

A small model never acts solo.

- swarm_tag: `ow-bench-trio` — the assembly is the bench trio
  run as a cross-family divergence-probe assembly (Qwen ·
  DeepSeek · Meta).
- Solo prohibitions for every lower-tier row: judgment calls ·
  canon writes · sends · verification-of-record · security
  decisions.
- Record entry: a small model's output enters the record only
  through a deterministic form gate (the STD-0 verifier) or a
  higher-tier verifier.
- Fork B: the assembly satisfies the no-self-moderation rule —
  3 distinct families sit in the assembly, and no family
  moderates its own floor; the verifier of record stands
  outside the assembly (frontier seat or the deterministic
  gate).

## Promotion path

A row leaves BENCH only on its trial's proof landing in the
record: the round-trip plus the ticketed completion, read back.
Promotion to SEATED is a seating decision under can.seats, not
an annotation edit.
