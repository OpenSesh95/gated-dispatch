# Defect register — defect-to-regression (C-029 H-C2)

Every defect names its permanent gate-suite regression test in
the same filing, or carries NEEDS-TEST as an open item (S-12
re-names it on the Sunday pass until closed). The mechanism is
adopted for the test program; the doctrine as fleet law is
Council-bound (CB-C29-1) and not presumed here.

| defect | filed | regression test | status |
|--------|-------|-----------------|--------|
| Unmetered served model raised a raw KeyError dressed as a provider error (gate v0.3.2) | 2026-11-12 | test_slice.py unmetered-served-model cases + SliceTest error-row pins | PINNED |
| Queue waiter-id collision across ledgers + cli snapshot shadowing (v0.4.0 build) | 2026-11-12 | threaded contention proof in the C-026 build record + queue tests in test_std0.py | PINNED |
| Responses-API success body carries "error": null — truthy-key check misread it as failure (v0.3.5) | 2026-11-12 | test_std0.py provider-shape tests (null-error case) | PINNED |
| seat_mode named build — composition-vs-chain defect class (assembly trial) | 2026-11-12 | test_named_mode_invariants_for_the_meter + named-mode suite | PINNED |
| Assembly REDUCE defect — emitted headers must parse to their element count (owner: assembly trial desk) | 2026-11-12 | parser-round-trip case, assembly trial home | NEEDS-TEST (owner's suite) |
| Scorer v1 pair — S5 anchor substring · out-of-range pointer rule (owner: trial scorer desk) | 2026-11-12 | scorer regression cases, SCORES.md disclosure | NEEDS-TEST (owner's suite) |
| Bench writer read a missing env as prod (§5.10 rule 1 conformance) | 2026-11-12 | test_pre_delta_record_reads_pre_delta_not_prod | PINNED |
| Preflight cert check read `detail` before initialization (v0.4.6 build) | 2026-11-12 | test_preflight_blocks_an_uncertified_leg | PINNED |
| Form-gate mutant survivor: qed-shape — term present, substance absent passes verify (H-D2) | 2026-11-12 | FIXED 2026-11-12 (C-041 R1): verify gains verdict mode (anchored terms + verdict structure); mutant kill rate 1.0 | CLOSED-KILLED |
| Form-gate mutant survivor: term-in-noise — anchor term buried in filler passes the substring check (H-D2) | 2026-11-12 | FIXED 2026-11-12 (C-041 R1): same anchored-verdict fix; mutant kill rate 1.0 | CLOSED-KILLED |
| Registry conversion: 2 rows shared one suffix string; the batch replace landed deepseek's ticket (0002) on the llama row — caught by PM's file-level verification, corrected to 0003 same cycle | 2026-11-12 | NEEDS-TEST — rule: identical-suffix batch edits assert per-row citations after write | OPEN |
| Lighthouse BURST-001 (external exhibit, burst run log): qwen3:14b volume leg — reasoning channel consumed the 1024-token output cap, content empty, form gate failed; NW-PROOF reads YES-partial (llama + deepseek legs landed). Gate-side: qwen3 + deepseek-r1 now declare cap_class "reasoning" in contracts.py (v0.4.8); engagements need a larger cap or reasoning-channel handling in the lane call shape | 2026-11-12 | contracts declaration test (test_reasoning_models_declare_the_reasoning_cap_class) | PINNED (declaration); lane call-shape handling OPEN |

| Gate crash: verify() raised TypeError on a None completion text (provider response with no content channel) | 2026-11-12 | Surfaced by the C-038 Wave 2 bench's first leg; verify now coerces None to empty at the chokepoint; regression test pinned | CLOSED-FIXED |
