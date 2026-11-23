"""Router brain — a model in the classification chair (his escalation
2026-11-19: production cutover on a compressed calendar; the design is
goal files/router-brain-shortlist-and-switch-design-2026-11-19.md).

The brain ADVISES; the table governs.

- classify() dispatches ONE named-mode call through cli.run to the
  winning seat (mistralai/mistral-large-2512 via OpenRouter — probe
  GD-20261119-0001..0040: class 8/8, form 8/8, $0.000187/decision) under
  loop_class "router-brain" and the C-039-registered prompt below. The
  module verifies its own prompt text against the catalogue row before
  dispatching; a mismatch or a missing row means no dispatch.
- The brain may raise rigor freely. It may NOT downgrade a
  stamper-named judgment class (routing.JUDGMENT_CLASSES) or
  qr-draft-check: a differing brain answer there is refused and the
  stamper's class stands, stamped downgrade_refused.
- Deterministic classes never reach the brain (the table is exact and
  free there), and TEST-0 precedes the brain: a compartmented input
  classifies by rule, its content never leaves for an external seat.
- ANY failure — transport, empty return, unparseable output, unknown
  class — returns the table's answer with fallback=True. The table is
  never a dependency of the brain; the brain is a dependency of
  nothing. classify() never raises into its caller.

Output budget: the transport helper's default applies. The winner is a
non-reasoning seat (its probe outputs ran to a few hundred tokens at
most); the >=3000-token budget rule binds the reasoning seats — if the
appeals seat (kimi-k3) is ever wired into this chair, its budget is set
first, per the probe's empty-at-cap exhibits.
"""

from __future__ import annotations

import hashlib
import json

from . import cli, lanes, prompts, routing

BRAIN_MODEL = "mistralai/mistral-large-2512"
BRAIN_PROVIDER = "openrouter"
PROMPT_ID = "router-brain"
GUARDED_CLASSES = set(routing.JUDGMENT_CLASSES) | {"qr-draft-check"}
DETERMINISTIC_CLASSES = {"qr-life-ops", "qr-career-ops", "ad-hoc"}
VALID_SPLITS = {"claude", "spark", "either"}

PROMPT_TEXT = """You classify work for a routing table. Classes (id: definition):
qr-quick-lookup: a factual lookup with a definite answer - INCLUDING single-fact status checks (reachability, counts, current state, one system's output, a status summary of current state) even when a tool must be run to get the answer; if the answer is one definite fact or a flat status list, it is a lookup, not research
qr-life-ops: household/personal logistics ONLY - deterministic plain compute; work-operations analysis is never life-ops
qr-career-ops: job-search operations - deterministic plain compute
qr-research: open research requiring synthesis across sources; measurement, scanning, or verification with a definite method is research when it synthesizes or analyzes - a single-system status check is a lookup instead
qr-live-wire: summarizing or monitoring a live feed (headlines, wires, tickers, sentiment) as it moves
qr-spiritual-study: study of spiritual texts and practice under a gold-source discipline
qr-canon-drafting: drafting canon, standards, or design-doctrine text that will govern other work; PLANNING a sequence of operations is not drafting - class a plan by the domain it operates on
qr-content-voice: drafting outward content in the owner's voice
qr-coding-burst: AUTHORING or MODIFYING code in a burst; running an existing tool, scanner, check, or verification - even a technical one - is NOT coding-burst; class tool-running by its purpose (measurement/verification is qr-research, a status check is qr-quick-lookup)
qr-draft-check: checking an outward draft against a rule sheet - verdicts only, never drafting
qr-commission-ruling: a commissioned ruling or design decision
qr-panel-verdict: a multi-seat panel verdict
qr-combination: a composite task spanning classes; name the dominant class
ad-hoc: an unclassifiable one-off human act
Boundary cases (class: the correct call):
- "Scan a repository's history with a security scanner and summarize the hits" -> qr-research (measurement; no code is authored)
- "Verify a control refuses X and passes Y, with fresh evidence" -> qr-research (verification, not code work)
- "Plan the step sequence for an operations rollout" -> the ops domain it serves, e.g. qr-career-ops (a plan is not a drafted document)
- "Check whether a web page is reachable and report its status" -> qr-quick-lookup (one definite fact)
- "Summarize today's CI failures and name the failing items" -> qr-quick-lookup (current-state status, not open research)
- "Compute rates from a results ledger" -> qr-research (analysis over data; never qr-life-ops)
Natures: deterministic (plain compute, no model judgment) - algorithmic (a fixed procedure with model steps) - statistical (pattern inference over data) - reasoning (multi-step inference to a conclusion) - probabilistic (judgment under uncertainty).
Seats: claude (the API seat - fires immediately) - spark (a browser-seat agent - queued, minutes-to-hours, strong at web research and long-horizon web tasks) - either.
Deterministic plain compute is classed qr-life-ops or qr-career-ops and is never split to a model seat.
Answer with ONLY a JSON object: {"class": "<class id>", "nature": "<nature>", "split": "claude|spark|either", "dominant": "<class id or null>"}. No other text."""


def _table_answer(stamper_class: str | None) -> str:
    if stamper_class in routing.CLASS_NATURE:
        return stamper_class
    return "qr-quick-lookup"


def _result(class_id, *, source, fallback, split=None, dominant=None,
            downgrade_refused=False, ticket_id=None):
    return {
        "class": class_id,
        "source": source,  # brain | table-fallback | table-deterministic | table-test0 | table-guarded
        "fallback": fallback,
        "split": split,
        "dominant": dominant,
        "downgrade_refused": downgrade_refused,
        "ticket_id": ticket_id,
    }


def _capture_parser(provider: str, sink: dict):
    """Wrap the provider parser so classify() can read the completion
    text (the STD-0 ticket does not carry it). Restored by the caller."""
    original = lanes.PARSERS[provider]

    def wrapped(raw):
        completion = original(raw)
        sink["text"] = completion.text
        return completion

    return original, wrapped


def classify(task_text: str, *, stamper_class: str | None = None,
             sensitivity: str = "internal",
             ledger_path: str, registry_path: str,
             run=cli.run) -> dict:
    """Classify one intake task. Returns the result dict; never raises."""
    table = _table_answer(stamper_class)

    # TEST-0 first: compartmented content never reaches an external seat.
    if sensitivity == "compartmented":
        return _result(table, source="table-test0", fallback=True)
    # Deterministic classes are the table's, exactly and for free.
    if stamper_class in DETERMINISTIC_CLASSES:
        return _result(table, source="table-deterministic", fallback=False)

    # The module's own priming check: the catalogue row must exist and
    # its hash must match the text this module sends.
    row = prompts.lookup(registry_path, PROMPT_ID)
    if row is None or row.get("sha256") != hashlib.sha256(
            PROMPT_TEXT.encode("utf-8")).hexdigest():
        return _result(table, source="table-fallback", fallback=True)
    stamp = prompts.build_stamp([row])

    manifest = {
        "life_domain": "UNCLASSIFIED",
        "life_domain_candidate": "operations",
        "query_nature": "classification",
        "data": {"source_class": "live", "provenance": "router-brain intake",
                 "sensitivity": sensitivity},
    }

    sink: dict = {}
    original, wrapped = _capture_parser(BRAIN_PROVIDER, sink)
    lanes.PARSERS[BRAIN_PROVIDER] = wrapped
    try:
        ticket = run(
            prompt=PROMPT_TEXT + "\n\nTASK: " + task_text,
            model=BRAIN_MODEL,
            provider=BRAIN_PROVIDER,
            ledger_path=ledger_path,
            prompt_stamp=stamp,
            loop_class="router-brain",
            routing_class=None,
            nature=None,
            seat_mode="named",
            input_manifest=manifest,
            auto_approve=True,
        )
    except Exception:
        return _result(table, source="table-fallback", fallback=True)
    finally:
        lanes.PARSERS[BRAIN_PROVIDER] = original

    if not isinstance(ticket, dict) or ticket.get("status") != "approved":
        return _result(table, source="table-fallback", fallback=True,
                       ticket_id=(ticket or {}).get("ticket"))
    text = (sink.get("text") or "").strip()
    try:
        parsed = json.loads(text[text.index("{"):text.rindex("}") + 1])
        brain_class = parsed["class"]
        split = parsed.get("split")
        dominant = parsed.get("dominant")
    except Exception:
        return _result(table, source="table-fallback", fallback=True,
                       ticket_id=ticket.get("ticket"))
    if brain_class not in routing.CLASS_NATURE or split not in VALID_SPLITS:
        return _result(table, source="table-fallback", fallback=True,
                       ticket_id=ticket.get("ticket"))
    if dominant is not None and dominant not in routing.CLASS_NATURE:
        dominant = None

    # Downgrade guard: a stamper-named guarded class stands.
    if stamper_class in GUARDED_CLASSES and brain_class != stamper_class:
        return _result(stamper_class, source="table-guarded", fallback=False,
                       split=split, dominant=dominant, downgrade_refused=True,
                       ticket_id=ticket.get("ticket"))
    return _result(brain_class, source="brain", fallback=False, split=split,
                   dominant=dominant, ticket_id=ticket.get("ticket"))
