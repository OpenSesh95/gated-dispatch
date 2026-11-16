"""Verification: deterministic checks on a completion before it can
reach the approval gate. A completion that fails verification is
recorded in the ledger as rejected and never gated.
"""

import json
from dataclasses import dataclass, field


@dataclass
class Verification:
    passed: bool
    checks: dict = field(default_factory=dict)


def _anchored(term: str, text: str) -> bool:
    """A term is anchored when it appears as the whole text, as a
    standalone line, at a line start, or on a labeled verdict line —
    not merely as a substring buried in filler."""
    stripped = text.strip()
    if stripped == term:
        return True
    for line in text.splitlines():
        line = line.strip()
        if line == term or line.startswith(term):
            return True
        if line.lower().startswith("verdict:") and term in line:
            return True
    return False


def verify(
    text: str,
    required_terms=(),
    max_chars: int = 20000,
    expect_json: bool = False,
    expect_verdict: bool = False,
) -> Verification:
    # A completion can arrive with text=None (a provider response with
    # no content channel — reasoning-only or empty choices). The gate
    # treats it as empty text, never as a crash (defect surfaced by
    # the C-038 Wave 2 bench, 2026-11-12).
    if text is None:
        text = ""
    checks = {}
    checks["non_empty"] = bool(text and text.strip())
    checks["within_max_chars"] = len(text) <= max_chars
    for term in required_terms:
        checks[f"contains:{term}"] = term in text
    if expect_verdict:
        # Verdict-shaped engagements (C-041 R1, the H-D2 fix class):
        # required terms must be ANCHORED. A bare echo of the term
        # with no verdict structure, or the term buried in noise,
        # is form-complete and substance-absent — it fails here.
        for term in required_terms:
            checks[f"anchored:{term}"] = _anchored(term, text)
        checks["verdict_structure"] = any(
            line.strip().lower().startswith("verdict:")
            or line.strip() in ("ACCEPT", "REJECT", "PASS", "FAIL")
            for line in text.splitlines())
    if expect_json:
        try:
            json.loads(text)
            checks["valid_json"] = True
        except (ValueError, TypeError):
            checks["valid_json"] = False
    return Verification(passed=all(checks.values()), checks=checks)
