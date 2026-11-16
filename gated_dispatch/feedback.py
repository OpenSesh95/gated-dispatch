"""Per-prompt emoji feedback capture (his directive 2026-11-15 12:51 CT).

Every routed output carries its ticket id + prompt id (the routing
stamp makes this possible). HIS emoji reaction on the message carrying
that output is the EXPLICIT satisfaction signal. This module is the
emitter: it appends outcome events to the router-side JSONL feed that
FinOps' routing.outcome class mirrors (ROUTER-FEEDBACK-CLASS.md,
MIRRORED, JSONL-first).

Charter law, binding here:
  - Silence = unknown, never satisfaction. This module has no API for
    silence; an unreacted output writes NO row.
  - The corrective-follow-up signal is INFERRED and weighted below the
    emoji-explicit signal (explicit 1.0, inferred 0.5). The Friday
    read prints the two lines separately, never merged.
  - G7: no query text, no user identifiers, no content. A row holds
    ids and the signal only.
  - An unknown emoji is rejected, never guessed. A reaction on a
    message carrying no ids is unmatched and writes no row.
"""
from __future__ import annotations

import json
import time

# The fixed feedback lexicon. Distinct from the Variant A / Gold
# Standard status markers (done/blocked/in-flight/pin/ask/action/
# cost/time glyphs), which are status, NOT feedback.
LEXICON = {
    "\U0001F44D": "satisfied",     # thumbs up
    "\U0001F44E": "failed",        # thumbs down
    "\U0001F501": "rework",        # repeat button
    "\U0001F31F": "exceptional",   # glowing star
}

# Signal -> the mirrored class's outcome_kind vocabulary.
OUTCOME_KIND = {
    "satisfied": "accepted",
    "failed": "failed",
    "rework": "corrected",
    "exceptional": "accepted",   # + exceptional=True on the row
}

WEIGHT_EXPLICIT = 1.0
WEIGHT_INFERRED = 0.5


def signal_for_emoji(emoji):
    """Map a reaction emoji to its feedback signal. Unknown -> raise."""
    try:
        return LEXICON[emoji]
    except KeyError:
        raise ValueError("not a feedback emoji: %r" % (emoji,))


def record_feedback(feed_path, *, ticket_ref, prompt_id, routing_class,
                    lane, model, emoji=None, signal=None, source="user"):
    """Append one outcome event to the router feedback JSONL feed.

    Exactly one of emoji / signal is given. emoji is the explicit path
    (source="user", weight 1.0). signal with source="inferred" is the
    corrective-follow-up path (weight 0.5). Returns the row written.
    """
    if (emoji is None) == (signal is None):
        raise ValueError("give exactly one of emoji / signal")
    if emoji is not None:
        signal = signal_for_emoji(emoji)
        if source != "user":
            raise ValueError("an emoji signal is always source=user")
        weight = WEIGHT_EXPLICIT
    else:
        if signal not in OUTCOME_KIND:
            raise ValueError("unknown signal: %r" % (signal,))
        if source != "inferred":
            raise ValueError("a bare signal is the inferred path only")
        weight = WEIGHT_INFERRED
    row = {
        "event_kind": "outcome",
        "event_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        "ticket_ref": ticket_ref,
        "prompt_id": prompt_id,
        "query_class": routing_class,
        "route_taken": "%s/%s" % (lane, model),
        "outcome_kind": OUTCOME_KIND[signal],
        "signal": signal,
        "exceptional": signal == "exceptional",
        "feedback_source": "user" if source == "user" else "downstream_desk",
        "signal_origin": source,
        "signal_weight": weight,
        "corrected_class": None,
        "reroute_target": None,
    }
    with open(feed_path, "a", encoding="utf-8") as fh:
        fh.write(json.dumps(row, sort_keys=True) + "\n")
    return row
