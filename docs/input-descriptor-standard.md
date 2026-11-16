# The Input Descriptor Standard (C-047) — v1.0, filed 2026-11-13

Status: FILED as the standing standard for input description. Feed-field adoption is proposed to Treasury under the §7 pattern (flagged with the commission's tasking); until acceptance, manifests ride run records and bench summaries.

## Why

C-039 standardized the prompt. Task sets are versioned and hashed. But two runs with identical prompt stamps could still be completely different runs — one on fresh filed data, one on stale or synthetic data — because the INPUT around the prompt was never stamped. This standard closes that layer.

## The manifest (one per run, beside the prompt stamp)

1. **Life-domain category** — what the task IS in real life, from the controlled vocabulary below (v1.0). His direction (2026-11-13): real-life use-case lines — daily searches · generic searches · trending topics · cooking · cleaning · chores — extended across his life domains. The operational loop/workload class remains the second axis (how the system runs it); the manifest carries both, neither replaces the other.
2. **Data descriptor** — source class (filed · public · synthetic · live) · provenance pointer/hash · size/shape beyond the token band · freshness watermark where applicable · sensitivity/compartment class (public · internal · sensitive · compartmented).
3. **Query-nature class** — lookup · synthesis · judgment · verification · extraction · generation · monitoring · classification · planning. This is DESCRIPTION; the question_key hash remains the fingerprint beside it, never a substitute.
4. **Injected-context manifest** — the C-039 recipe id + version (what SHOULD be injected) PLUS the run-time record of which source snapshots were actually pulled, at what watermarks (what WAS). The distinction between the two is the standard's core.
5. **Reproducibility rule** — a run counts as REPRODUCIBLE only when the prompt stamp AND the input manifest are both complete. The bench summary carries input_manifest + reproducibility fields beside run_validity; the C-040 audit receipt gains the input lines (below).

## Controlled vocabulary v1.0 — life domains

daily-search · generic-search · trending-topics · cooking · cleaning · chores · news-briefings · scheduling · shopping · health · home · finance · travel · learning · devotional-festival · family-social · work-career · operations · research · entertainment

**Amendment rule:** additions enter as versioned amendments to this standard (vocabulary v1.1, v1.2, …) — never as ad-hoc strings on a stamp. A category that cannot be placed stamps `UNCLASSIFIED` with the candidate string preserved in `life_domain_candidate` for the amendment pass (enforced by gated_dispatch.inputs.validate_manifest; test-pinned).

## The audit-receipt block (C-040 format, extended)

Every bench's completeness receipt gains two lines:

```
inputs:    life-domain STAMPED|UNCLASSIFIED|MISSING · query-nature STAMPED|MISSING · data-descriptor STAMPED|MISSING · context-manifest STAMPED|MISSING
repro:     REPRODUCIBLE | NON-REPRODUCIBLE (missing: <named>)
```

A bench whose receipt shows NON-REPRODUCIBLE publishes with that line visible — the same discipline as the judge-calibration line.

## Machinery

`gated_dispatch/inputs.py` (gate v0.4.20): the vocabularies as versioned constants · validate_manifest (the completeness gate) · reproducibility (the rule at the summary layer). cli.run accepts input_manifest; the final + stopped feed records carry it; bench summaries cite it.
