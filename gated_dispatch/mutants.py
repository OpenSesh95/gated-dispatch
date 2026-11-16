"""Form-gate mutation tests (C-029 Group D, H-D2).

A standing mutant set run per-change on form-gate/scorer code
and monthly. The gate's score is its mutant kill rate. A
surviving mutant becomes a defect under H-C2 — it files, it
does not hide.

Mutants are engagements: (name, text, verify kwargs, and the
verdict a CORRECT gate returns). Survival = the live gate
returns the wrong verdict.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone

from . import verify as verify_mod

# (name, text, kwargs, correct_pass)
MUTANTS: list[tuple[str, str, dict, bool]] = [
    # form-complete, content-absent: in a VERDICT-SHAPED engagement
    # the term is present, the substance is not — a correct verdict
    # gate rejects it (the engagement shape is part of the mutant;
    # C-041 R1 added the gate's verdict mode that reads it)
    ("qed-shape", "lane live",
     {"required_terms": ("lane live",), "expect_verdict": True}, False),
    # the anchor term buried in filler: substring presence is
    # not an anchored verdict
    ("term-in-noise", ("filler " * 400) + "lane live" + (" filler" * 400),
     {"required_terms": ("lane live",), "expect_verdict": True}, False),
    ("whitespace-only", "   \n  ", {}, False),
    ("empty", "", {}, False),
    ("json-trailing-prose", '{"a": 1} and here is why',
     {"expect_json": True}, False),
    ("oversized", "x" * 20001, {}, False),
    ("header-without-separator", "VERDICT\nPASS",
     {"required_terms": ("VERDICT:",)}, False),
    # case-sensitive anchor: the spec is exact-match; a correct
    # gate rejects the case variant (killed = correct here)
    ("term-case-variant", "LANE LIVE",
     {"required_terms": ("lane live",)}, False),
    # the control: a clean return must pass
    ("control-clean", "lane live",
     {"required_terms": ("lane live",)}, True),
]


def run_mutants(findings_path: str | None = None) -> dict:
    killed, survived = [], []
    for name, text, kwargs, correct_pass in MUTANTS:
        result = verify_mod.verify(text, **kwargs)
        if result.passed == correct_pass:
            killed.append(name)
        else:
            survived.append(name)
    out = {"ts": datetime.now(timezone.utc).isoformat(timespec="seconds"),
           "mutants": len(MUTANTS), "killed": killed,
           "survived": survived,
           "kill_rate": round(len(killed) / len(MUTANTS), 4)}
    if survived and findings_path:
        with open(findings_path, "a", encoding="utf-8") as fh:
            for name in survived:
                fh.write(json.dumps({
                    "ts": out["ts"], "sensor": "H-D2",
                    "class": "mutation-survivor",
                    "fact": f"mutant {name} survived the form gate",
                    "evidence": ["gated_dispatch.mutants set"],
                }, sort_keys=True) + "\n")
    return out
