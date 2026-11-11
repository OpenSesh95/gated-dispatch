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


def verify(
    text: str,
    required_terms=(),
    max_chars: int = 20000,
    expect_json: bool = False,
) -> Verification:
    checks = {}
    checks["non_empty"] = bool(text and text.strip())
    checks["within_max_chars"] = len(text) <= max_chars
    for term in required_terms:
        checks[f"contains:{term}"] = term in text
    if expect_json:
        try:
            json.loads(text)
            checks["valid_json"] = True
        except (ValueError, TypeError):
            checks["valid_json"] = False
    return Verification(passed=all(checks.values()), checks=checks)
