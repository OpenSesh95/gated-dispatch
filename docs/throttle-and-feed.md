# Throttle v1 + dispatch feed (schema v1.1)

Two mechanisms wrap every gated dispatch. Both live in the gate;
callers change nothing except passing `--loop-class`.

## Throttle table v1 — intelligent throttling

`gated_dispatch/throttle.py` holds the table as data:

- **Allowlist.** Only concrete model ids in `MODELS` dispatch. Any
  id containing `latest` is banned (an alias is an unpinned model).
  `gemini-2.5-flash` is retired by name. The allowlist never outruns
  the price table (a test pins the invariant).
- **Error budgets.** Per model: N errors inside a rolling window
  breach the budget and start a cooldown (Gemini: 3 errors / 10 min
  → 30 min cooldown; frontier seats: 3 / 10 min → 15 min).
- **Concurrency + spacing.** Per model. The Gemini free-tier quota
  is the binding constraint: google lane concurrency 1, minimum
  4 s between calls.
- **Backoff.** Exponential per model (base × 2^attempt, capped);
  retryable failures are connection/timeout class plus provider
  error bodies, which the lane layer normalizes to ConnectionError.
- **Class behavior (SLO axis).** `panel · commission · ruling`
  fail closed: a breached lane stops the dispatch
  (`blocked-throttle:error-budget`); substitution needs an explicit
  per-instance decision. `junior · defect · lower-order` degrade:
  the resolver walks the commodity chain — gemini-3.8-flash →
  grok-4.20-0309-non-reasoning → claude-haiku-5-5 — to the first
  model inside budget, and the degrade is written on the ticket
  checks and the dispatch record (`degraded_from`). Unknown classes
  fail closed. Legacy caller names (sweep, council, …) normalize
  onto the SLO axis; the record carries the SLO class only.

State (error timestamps, cooldowns, in-flight counts) is one JSON
file beside the ledger, mutated under a lockfile.

## Dispatch feed — schema v1.1

`gated_dispatch/dispatch_log.py`. One record per attempt; attempts
of a loop share `loop_id` = the gate ticket id. A loop stopped
before firing writes one `attempt_no: 0` record banded on the
prompt estimate (`band_basis: prompt-estimate`).

Fields: loop_id · loop_class · seat (provider family) · model ·
attempt_no · ts_dispatch · ts_outcome · latency · size_band
(mechanical ≤25k · execution ≤60k · reasoning ≤120k · L4, on
attempt tokens in+out) · band_basis · tokens_in · tokens_out ·
cost_usd · cost_source (ticks · list · grant-offset · free-tier ·
local-zero) · outcome (success · fail · partial — partial = the
call returned, the loop did not approve) · form_gate_pass,
owner_surface_ts, owner_tap_ts, run_outcome (final attempt only;
owner timestamps null on auto-approved runs) · trace_fidelity
(null — UNMEASURED at this layer, sampler-owned) · degraded_from ·
question_key · question_shingles.

cost_source rules: xAI = ticks when the response carries
`cost_in_usd_ticks` (converted at 1 tick = 1e-10 USD), else list;
google = list (paid tier since 2026-11-12 19:28 CT; the label read free-tier before the P-024 item 1 fix); local (own hardware) = local-zero; the GCP
lane takes grant-offset when it wires; everything else = list.

Retrieval-before-generation: question_key is the ticket's prompt
SHA-256; question_shingles are hashes of normalized word 3-grams
(cap 32). Hashes only — no raw text enters the feed. The reference
`summarize()` computes per loop class: attempts, p50/p95 latency,
outcome counts, and the repeat-question rates under schema v1.2
(Treasury SLO-TABLE §5.2): the exact-match rate and the fuzzy-match
rate (shingle Jaccard ≥ 0.8) publish side by side, never blended;
fuzzy matching requires ≥ 8 shingles on both loops (small-set
floor); counted loops sit in the 7-day window but the match search
reaches back over all retained records; a repeat requires the
earlier loop to have ended in success (a re-ask after a failed
loop is a retry). Report-only in v1 — no SLO target until a
baseline exists. The production read lives in Treasury's meter
layer.

## Speed Tranche additions (v0.3.1)

**Hedged requests (item 2).** `--hedge` on a commodity class
(junior · defect · lower-order) fires the resolved model and the
next chain model in parallel. The first returning completion wins
and proceeds through verification and the gate; the loser is
cancelled — joined for a 5 s grace, then abandoned (daemon
thread), and its attempt record reads `outcome: superseded` with
its real tokens and cost when it settled inside the grace. Both
attempts stay inside the stamp cost ceiling. Deliberative classes
never hedge. V1 boundary: the winner is the first RETURNING
completion; verification applies to the winner alone (no fallback
to the loser on a verification fail), and a loser abandoned past
the grace can return unmetered tokens — bounded by the 1024
max-token cap and named here so the meter desk can weigh it.

**Stall cause (item 1c).** The final record of a stopped loop
carries `stall_cause`: unmetered · envelope · hold ·
banned-model · error-budget · chain-exhausted · concurrency ·
provider-error · verification · gate. Approved loops carry null.

**Hop count.** `hop_count` (caller-passed, default 0) rides the
final attempt record only. The gate stores it and never computes
it; Treasury derives execution / queue / transit from it with the
record's latency and owner timestamps.

## Class-priority queue (C-026 line 1, v0.4.0)

Contended slots grant in class order with aging. Waiters register
in the throttle state; only the head may acquire. Ranks: ruling 0 ·
commission 1 · panel 2 · junior 3 · defect 4 · lower-order 5.
Aging: effective rank −1 per 45 s waited (floor 0); ties break by
arrival. `queue_wait` on the feed record measures the queued wait.
The hedge path acquires directly (opportunistic by design).

## Named-seat measurement mode (v0.3.8) + standing riders

`--seat-mode named` fires the requested seat as itself, outside
the commodity chain, for measurement only; the record declares
the mode. **GL-28 rider (C-030, standing text): chain-only
measurement stands CLOSED at gate v0.3.8 — chain-only restriction
of measurement lanes is prohibited.**

**Probation scope (GL-15, C-030, rule text):** the R-2 probation
quarantine reads **service-only**. Measurement (seat_mode named)
is exempt by rule: a named run is never blocked by the
quarantine, and its errors never set it. The error budget and
cooldown remain general throttle discipline in both modes.
