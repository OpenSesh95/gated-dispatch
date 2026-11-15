# Masking — PII at the dispatch seam

Status: PROPOSAL (Sudoers shape: this PR is the proposal; review is the
council review; merge is ratification). Adopted design: Q-056 (2026-11-14).
Nothing here wires into live dispatch yet — the seam integration lands in a
follow-up PR after ratification.

## The pattern

Every frontier-bound prompt passes through the masker before dispatch.
Personal information is replaced with typed tokens; the frontier answers
against tokens; the response is re-identified through a per-ticket vault
before it reaches the consumer, and leak-scanned on the way in.

1. **Outbound mask** — deterministic layer (Luhn cards, structural SSNs,
   email/URL/IP, phone forms) + the operator's class register (names ->
   role tokens, orgs -> class tokens, always-tokenize strings, name-part
   gazetteer, never-mask keep-set) + neural detectors behind a seam.
2. **Vault** — the (token -> original) map, scoped to one ticket, held on
   the gate host only, dropped at ticket close. The ledger records counts
   by class, never values.
3. **Dispatch** — the STD-0 ticketed call runs on masked text; the ticket
   gains masking counts as metadata.
4. **Inbound** — re-identify via the vault, then leak-scan: any register
   or vault original appearing without token provenance quarantines the
   response (the consumer sees the defect, not the text).
5. **Fail-closed** — any masker error blocks dispatch. No bypass.

## Engines (pilot, 2026-11-14, pinned set v1, 40 texts)

| Class | Rampart | Presidio |
|---|---|---|
| Names recall | 1.000 | 0.786 |
| Identifiers recall | 0.900 | 0.900 |
| Keep-set retention | 0.750 | 0.438 |
| Latency p50 | 8.2 ms | 8.1 ms |

- **Rampart** (primary) — 14.7 MB local ONNX classifier + deterministic
  layer; its per-conversation session table is the vault pattern,
  implemented. CC BY 4.0. Pinned by hash in deployment.
- **Presidio** (fallback / breadth) — second pass for classes outside
  Rampart's 17 labels, unknown-org NER, and non-Latin content (Rampart's
  documented out-of-scope). MIT.
- The pilot's keep-set leg failed the 90% bar on both engines raw; the
  register keep-set in this module is the correction, and the pilot's
  over-masks are this PR's regression shapes. Retention with the keep-set
  active must hold >= 90% on the pinned set before the wiring PR lands —
  that condition is part of this proposal.

## Scope honesty

- The masker covers API lanes, where a seam exists. Consumer/UI seats
  cannot be proxied; they keep the class-gating discipline.
- The real class register is operator data and is never committed;
  `register.example.json` carries the shape with synthetic values only.
- A missed detection creates false confidence — worse than an honestly
  unmasked lane. The counterweights are the leak scan, the deterministic
  layer under both engines, and sampled audits of masked text.
