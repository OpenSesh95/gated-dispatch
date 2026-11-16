# SEAT FLOW — the operator document

How a seat is born, primed, proven, watched, and re-primed. Written
for the next operator. Two seat families run on this estate: the
Ollama model seat (Nightwatch, GCP) and the primed browser profiles
on gcp-worker (job-portal sessions). The flow is the same shape for
both: **born on the seat → primed on the seat → persistence proven by
a fresh load → watched by a canary → re-primed on exception, never
by the canary itself.**

## 1. Born on the seat
- The model seat (gcp-ollama-a, us-west1-a, g2-standard-4 + 1× L4)
  is born by cloning the retained snapshot
  (`gcp-ollama-draw1-20261114`), never by rebuilding from scratch —
  the snapshot carries the pulled models and their digests.
- HARD CONSTRAINT: the original gcp-ollama (us-central1-c,
  TERMINATED) must never run while the clone is up. They share one
  Tailscale machine identity; two live copies corrupt the tailnet
  record for both.
- Every birth and stop writes a duty row (start / stop / run_hours /
  class) to `ledger_bronze.nightwatch_duty_events`. A seat that is
  running without a duty row is a record defect, not a detail.

## 2. Primed on the seat
- Browser profiles are primed ON the box that will use them
  (gcp-worker: `/opt/worker/profiles/<portal>` — LinkedIn, Dice).
  A profile primed elsewhere and copied over does not persist the
  same way; the session must be born where it will live.
- Priming is a sitting: a human-grade sign-in on the box, through
  the broker pattern. No credential is ever typed by a canary, a
  script, or this gate.

## 3. Persistence proof — the fresh load is the test
- An in-window read OVERSTATES state: a session can read signed-in
  inside its own window and still bounce to a login wall on a fresh
  load (measured 2026-11-16: a re-prime read signed-in at 13:57 CT;
  a fresh load bounced at 14:03 CT).
- The proof is therefore a FRESH persistent-context load of the
  signed-in surface (the session canary's check), never a read of
  the window that did the priming.
- For the model seat, the proof is digest verification: the served
  models' digests must match the deployment record (qwen3:14b ·
  deepseek-r1:14b · llama3.1:8b, digests on file in the Nightwatch
  closeout) before the seat takes work.

## 4. The canaries
- **Session canary** (repo: OpenSesh95/session-canary): on-box cron
  every 4 hours, one fresh-load pass per portal, no retry loops.
  States: ALIVE (silent) · DEAD · UNKNOWN · ERROR · NOT_PRIMED.
  A Geneva-side reader fetches the latest result over the tailnet
  on the same rhythm and folds it into watchdog reporting.
- **Served-model canary** (this repo, `gated_dispatch/canary.py`):
  weekly, Sundays ~14:36 CT, probes every seated model id once in
  named mode and files drift findings. It never edits a map —
  drift findings are proposals; a human or a ratified wave moves
  the map.

## 5. The re-prime loop
1. A canary reads DEAD / ERROR / NOT_PRIMED.
2. The reader raises an exception the same run: to CoS + the owning
   desk (Job Pipeline for portal seats), naming the portal and the
   re-prime act. Detection only — nothing re-primes automatically.
3. The re-prime is a sitting on the box (step 2), scheduled like
   any other owner act.
4. The seat returns to service only on a fresh-load ALIVE (step 3).
   A seat that reads ALIVE in the priming window but has not passed
   a fresh load is NOT back.

## 6. Promotion of this machinery
Code for the seat/pipeline machinery promotes dev → test → cert →
production under the enterprise protocol (see
`.github/workflows/promote.yml`). Cert is the owner's tap on the
test evidence. The production flow is never impacted by additions:
work lands on dev, verifies at each stage, and only a verified,
tapped change reaches production.
