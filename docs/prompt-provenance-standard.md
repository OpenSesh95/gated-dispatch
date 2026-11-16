# The Prompt Provenance Standard (C-039)

**Effective: 2026-11-12, on filing. Scope: NEW RUNS ONLY — no historical run is relabeled; tonight's existing records keep their labels.**
**Status: ADOPTED as the standing standard by his ruling, 2026-11-12 22:43 CT (via CoS), in force from tonight, prospective scope as filed. Implementation state: registry built + seeded · TS-PROMPT live in preflight · TS-SEC provenance probe live · feed fields landed under Treasury §5.11 · loop delta integration filed with the C-028 loop as a proposal (prompt-delta class) under its adoption path.**

The stack stamps model + task set + costs, but the prompt — the third input of every run — carried no stamp. This standard closes the gap in 6 parts.

## §1 The prompt registry

Versioned like Leela atoms (supersede, never overwrite). A record carries: prompt_id · species · version · author (seat or human) · template variables · changelog entry · **SHA-256 of the text — never the text**. Registry texts are access-ruled: prompts are IP and can carry compartmented material, so the text lives only at its source; the registry proves identity by hash.

Three species register separately: **system** (standing/system prompts) · **task** (per-run task prompts) · **context** (injected context recipes). Implementation: `gated_dispatch.prompts` + `docs/prompt-registry.jsonl`. Seeded at filing with the standing prompts in current production use (the 4 SM seat prompts as system v1 · the lane-live probe + the 2 W-1 harness prompts as task v1); their changelogs open at this standard's effective date. The context species opens empty; its first registration lands with its first production use.

## §2 The run stamp extension

A run's stamp carries, per species present: prompt_id + version + content hash — plus decoding parameters as a temperature class (deterministic · low · standard · creative · provider-default). The stamp completes the run identity: model + set + prompts + context + params + harness.

**Feed-field adoption — RULED by Treasury (SLO §5.11, 2026-11-12):** prompt_id, prompt_version, and decoding parameters are ADOPTED as feed-resident operational metadata. The content hash rides the feed AND the pre-registration record, with the layer condition that **the content hash stays out of the WS-4 dataset** (the dataset-schema exclusion row carries the note). Prompt texts stay in the access-ruled registry — no text in feed, pre-registration, or dataset. Landed at the gate: `cli.run(..., prompt_stamp=...)` stamps the final + stopped feed records (dispatch_log carries the field; null on pre-standard records). Bench summaries continue to cite the stamp.

Treasury's reasoning, recorded with the ruling (SLO §5.11): the layers never conflicted — question_key already lives in the feed as a hash while the schema excludes it from publication; the content-hash takes the same seat. At the operational layer a hash is an identity claim; at the publication layer a hash is a fingerprint. The interim run-records-only form of the stamp is RETIRED on this landing: stamps file in the feed under the adopted fields.

## §3 Validity rule — TS-PROMPT

A scored run without a complete prompt stamp reads **UNMEASURED**. The stamp joins TS-PRE as a preflight leg: a leg declaring `scored` must supply its prompt texts + registry; preflight verifies each text's hash against the registry and fails the leg (verdict BLOCKED) when any species is unregistered or the stamp is absent. `prompts.run_validity` states the rule at the summary layer.

## §4 Prompt deltas as experiments

A prompt change is a first-class loop delta: it registers as a new version (never a silent edit), and BEFORE/AFTER comparisons run through the loop's normal propose → gate path. **A prompt edit mid-bench invalidates the pairing**: `prompts.pairing_check` returns paired_valid=false with the reason on the record whenever two runs' stamps differ in any species hash or in temperature class — the delta is the experiment, and the bench says so rather than pairing across it.

## §5 TS-SEC provenance check

TS-SEC gains a provenance axis (`tssec.probe_provenance`): every prompt text in a run is hashed against the registry; **a hash matching no registered version is an anomaly on its face** — injection detection via provenance, complementing the content battery (which reads what a prompt says; provenance reads whether it is ours at all).

## §6 The §7 reconciliation

C-033 §7 carved prompt derivatives OUT of pre-registration (text protection), which left reproducibility incomplete. The reconciliation, written into both standards: **hashes go INTO pre-registration** (a pre-registration names prompt_id + version + hash per species, restoring reproducibility) · **texts stay in the registry** under its access rule (the carve-out's protection is preserved). No text enters a pre-registration, a bench record, or a dataset under this standard — only hashes, ids, and versions travel.

— Gate desk, 2026-11-12. Machinery: gate v0.4.14 (prompts.py · bench stamp citation · TS-PROMPT preflight leg · TS-SEC provenance probe).
