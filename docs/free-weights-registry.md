# Free-Weights Registry — C-031 WS-1

Registration batch 1 · 2026-11-12 · Source: the C-031 census
table presented at CoS 2026-11-12 21:02 CT (his go 21:11 CT).

Registration is not wiring, and wiring is not seating (program
rule). Every row below stands **REGISTERED** — priced $0.00 in
the gate with cost_source `free-tier`, carrying NO throttle
rule: the gate cannot resolve to an id it cannot fire. A row
becomes **PROVEN** only by a gated serving proof after its
host key lands (the key sitting is his, bundled by PM with the
Friday sittings). No row is SEATED by anything in this file.

## Classes on every row

- **License/terms class** — the model weights' license family.
  Rows marked VERIFY carry the class as presented; the proof
  run confirms it against the host's model card.
- **Data-policy class** (host) — `Z` zero-retention class:
  the host publishes no-training + minimal retention for API
  traffic; eligible for OSINT legs. `M` may-train class: the
  host or route may retain or train on traffic — **QUARANTINE
  for sensitive content** (Rule 2 containment): no private,
  personal, or employer-adjacent content ever routes to an
  M-class row. Host classes stand ASSUMED at registration
  (host-published pages), verified at the key sitting.

## Batch 1 — hosted free lanes

| id | provider | license class | data-policy | disposition |
|----|----------|---------------|-------------|-------------|
| gpt-oss-120b | groq | Apache-2.0 | Z (ASSUMED) | REGISTERED |
| gpt-oss-20b | groq | Apache-2.0 | Z (ASSUMED) | REGISTERED |
| qwen3.8-27b | groq | Apache-2.0 (VERIFY) | Z (ASSUMED) | REGISTERED |
| whisper-large-v3-turbo | groq | MIT | Z (ASSUMED) | REGISTERED |
| nemotron-3-ultra | openrouter | NVIDIA Open Model License | M — QUARANTINE-sensitive | REGISTERED |
| gemma-4-26b-a4b-it | openrouter | Gemma Terms of Use | M — QUARANTINE-sensitive | REGISTERED |
| gemma-4-31b-it | openrouter | Gemma Terms of Use | M — QUARANTINE-sensitive | REGISTERED |
| flint-v1.0 | openrouter | NEEDS-VERIFY | M — QUARANTINE-sensitive | REGISTERED |
| north-mini-code | openrouter | CC-BY-NC class (VERIFY) | M — QUARANTINE-sensitive | REGISTERED |
| gpt-oss-20b | openrouter | Apache-2.0 | M — QUARANTINE-sensitive | REGISTERED |
| llama-3.3-70b | sambanova | Llama Community License | Z (ASSUMED) | REGISTERED |
| deepseek-v3.1 | sambanova | DeepSeek Model License (VERIFY) | Z (ASSUMED) | REGISTERED |
| gpt-oss-120b | sambanova | Apache-2.0 | Z (ASSUMED) | REGISTERED |

Note the same weights under two hosts carry the HOST's data
class: gpt-oss-20b is Z on Groq and M on OpenRouter-:free.
Data policy follows the route, not the weights.

## Batch 1 — Ollama rotation candidates (lanes exist: local · gcp)

| id | license class | disposition |
|----|---------------|-------------|
| qwen3:32b | Apache-2.0 | REGISTERED — VM slot consumes the S-A pick when ruled; registration proceeds, the slot waits |
| gpt-oss:20b | Apache-2.0 | REGISTERED |
| gemma-4-27b | Gemma Terms of Use | REGISTERED (id form VERIFY at pull — registry name may carry the -it suffix) |
| 70B class (id at pick) | per pick | REGISTERED as a class row for the 96GB tier; the concrete id registers when the S-A pick lands |

Priced $0.00 under providers `local` and `gcp` beside the bench
trio; no throttle rule until a host proves serving.

## Batch 2 — roster completion (C-034, registered 2026-11-12, gate v0.4.11)

Same law as batch 1: registration ≠ wiring ≠ seating; disposition REGISTERED for every row; license + data-policy class on the row; data policy follows the ROUTE. Direct-API rows carry NO price entry (NEEDS-SOURCE until the key sitting prices them from the provider's own page) — the gate stops them as unpriced, which is the correct state. Hosted-free routes price $0.00 under their host provider with cost_source free-tier. Host data classes are ASSUMED (host-published), verified at the key sitting.

| Model id (gate form) | Family | License / terms | Routes (provider → data class) | Notes |
|---|---|---|---|---|
| kimi-k2 | Moonshot Kimi K2 | Modified MIT (weights) | groq → Z · openrouter → M · direct (Moonshot) → ASSUMED, unpriced | Direct API row registered-not-priced |
| mistral-large | Mistral Large | Proprietary (La Plateforme terms) | direct (Mistral) → ASSUMED, unpriced | No open weights |
| mistral-medium | Mistral Medium | Proprietary | direct → ASSUMED, unpriced | |
| codestral | Codestral | Mistral Non-Production License (weights) / API terms | direct → ASSUMED, unpriced | Code specialist |
| magistral | Magistral | Proprietary / research license by size | direct → ASSUMED, unpriced | Reasoning line |
| mistral-small | Mistral Small 3.x | Apache-2.0 | local · gcp → Z (self-hosted) | Local rotation candidate, $0.00 both lanes |
| devstral | Devstral | Apache-2.0 | local · gcp → Z (self-hosted) | Code agent line, local candidate |
| deepseek-chat | DeepSeek V3-class | DeepSeek Model License (weights); code MIT | openrouter → M · direct (DeepSeek) → ASSUMED, unpriced | SambaNova deepseek-v3.1 row stands from batch 1 (Z) |
| deepseek-reasoner | DeepSeek R1 (full) | DeepSeek Model License; code MIT | openrouter → M · direct → ASSUMED, unpriced | Full R1; the local lane holds the 14B distill |
| nemotron-super-49b | Nemotron Super | NVIDIA Open Model License | openrouter → M | Full line beyond the batch-1 Ultra preview row |
| nemotron-ultra-253b | Nemotron Ultra | NVIDIA Open Model License | openrouter → M | |
| qwen3-235b | Qwen3 flagship (MoE) | Apache-2.0 | openrouter → M | Hosted flagship; too large for the bench lanes |
| qwen3-coder | Qwen3 Coder | Apache-2.0 | openrouter → M | |
| qwen3-vl | Qwen3 VL | Apache-2.0 | openrouter → M | Vision line |
| llama-4-scout | Llama 4 Scout | Llama Community License | groq → Z · openrouter → M · sambanova → Z | |
| llama-4-maverick | Llama 4 Maverick | Llama Community License | groq → Z · openrouter → M · sambanova → Z | |
| glm-4.6 | GLM (Zhipu/Z.ai) | MIT (weights) | openrouter → M · direct (Z.ai) → ASSUMED, unpriced | Panel-found family; hosted only (355B class — no bench-lane row) |

VERIFY-at-proof (batch-1 rule): exact served id forms confirm at the key sitting + gated proof; a row whose served form differs registers the served form as its own row.

## OpenRouter lane wiring outcome (2026-11-12, gate v0.4.12)

Lane LIVE. Credential: the connector's stored key verified clean on the fourth entry (limit $250 · remaining $250 · usage $0 · expires 2027-02-11, per /api/v1/auth/key). The first 3 entries failed identically at the provider ("malformed credential") — the defect sat in the cloud-browser clipboard path and was eliminated by a local-browser entry. Gate-side limit reading: the key carries its own $250 cap; the account's free-model allowance (limits document: 1,000 free-model requests/day at $10+ lifetime purchases) is Treasury's standing figure — the gate reads the key's numbers, and the 2 readings do not conflict (they govern different scopes).

Per-row state:
- **WIRED + PROVEN** (serve form verified in the live catalog; TS-PRE PASS; ticketed named-mode proof approved): nemotron-3-ultra → nvidia/nemotron-3-ultra-550b-a55b:free (GD-20261113-0001) · flint-v1.0 → recursive/flint-v1.0:free (GD-20261113-0004) · north-mini-code → cohere/north-mini-code:free (GD-20261113-0005). Tickets on orproof.jsonl, cost $0.00, cost_source free-tier.
- **WIRED, UPSTREAM-LIMITED**: gemma-4-26b-a4b-it + gemma-4-31b-it (serve forms google/…:free verified in catalog; proofs failed on the upstream Google AI Studio shared-pool 429 across 3 attempts each; the rows sit in error-budget cooldown per throttle discipline; the Sunday canary re-probes them — they are throttle.MODELS rows now).
- **REGISTERED-NOT-SERVED** (no :free form in the current catalog; the lane refuses them by name — registered-not-served — rather than spending paid rates against a $0 registration): gpt-oss-20b · kimi-k2 · deepseek-chat · deepseek-reasoner · nemotron-super-49b · nemotron-ultra-253b · qwen3-235b · qwen3-coder · qwen3-vl · llama-4-scout · llama-4-maverick · glm-4.6. Paid forms exist in the catalog for most; seating any of them is a re-pricing + re-registration decision, not a wiring act.
- M-class enforcement is live at the gate: openrouter rows refuse ruling + commission classes (blocked-router:m-class, test-pinned).
- Wired ≠ seated: the wired rows hold throttle rules for proof discipline and enter NO chain; seating follows benches per C-031.
