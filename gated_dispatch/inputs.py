"""Input descriptor standard (C-047): the per-run INPUT MANIFEST.

C-039 standardized the prompt; this standardizes everything around
it. A run counts as REPRODUCIBLE only when the prompt stamp AND the
input manifest are both complete. The manifest carries TWO axes:
the LIFE-DOMAIN category (what the task IS in real life — his
direction, 2026-11-13) and the operational class (how the system
runs it). Neither replaces the other.

The vocabularies are CONTROLLED: additions enter as versioned
amendments to the standard, never ad-hoc strings on a stamp. A
category that cannot be placed files as UNCLASSIFIED with the
candidate string preserved for the amendment pass.
"""

from __future__ import annotations

VOCABULARY_VERSION = "1.0"

LIFE_DOMAINS = frozenset({
    # his named lines first (2026-11-13 direction)
    "daily-search", "generic-search", "trending-topics", "cooking",
    "cleaning", "chores",
    # extended across his life domains
    "news-briefings", "scheduling", "shopping", "health", "home",
    "finance", "travel", "learning", "devotional-festival",
    "family-social", "work-career", "operations", "research",
    "entertainment",
})

QUERY_NATURES = frozenset({
    "lookup", "synthesis", "judgment", "verification", "extraction",
    "generation", "monitoring", "classification", "planning",
})

SOURCE_CLASSES = frozenset({"filed", "public", "synthetic", "live"})
SENSITIVITIES = frozenset({"public", "internal", "sensitive",
                           "compartmented"})


def validate_manifest(m: dict | None) -> list[str]:
    """The completeness check. Returns the list of defects; an empty
    list means complete. Unknown vocabulary values are defects (the
    caller stamps UNCLASSIFIED instead — never an invented string)."""
    if not m:
        return ["manifest absent"]
    problems = []
    if m.get("life_domain") != "UNCLASSIFIED" and \
            m.get("life_domain") not in LIFE_DOMAINS:
        problems.append(f"life_domain not in vocabulary v{VOCABULARY_VERSION}")
    if m.get("life_domain") == "UNCLASSIFIED" and \
            not m.get("life_domain_candidate"):
        problems.append("UNCLASSIFIED without the candidate string preserved")
    if m.get("query_nature") not in QUERY_NATURES:
        problems.append("query_nature not in vocabulary")
    data = m.get("data") or {}
    if data.get("source_class") not in SOURCE_CLASSES:
        problems.append("data.source_class not in vocabulary")
    if not data.get("provenance"):
        problems.append("data.provenance missing (pointer or hash)")
    if data.get("sensitivity") not in SENSITIVITIES:
        problems.append("data.sensitivity not in vocabulary")
    return problems


def reproducibility(prompt_stamp: dict | None, manifest: dict | None) -> dict:
    """The C-047 rule, at the summary layer: REPRODUCIBLE only when
    both stamps are complete. The validity line names what's missing."""
    missing = []
    if not prompt_stamp:
        missing.append("prompt_stamp")
    problems = validate_manifest(manifest)
    if problems:
        missing.append("input_manifest:" + ";".join(problems))
    return {"reproducible": not missing,
            "missing": missing}
