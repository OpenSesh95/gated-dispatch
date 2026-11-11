"""Approval gate: a verified completion stops here until a human
approves it. Non-interactive runs must opt in explicitly with
auto_approve=True (used by tests and scheduled jobs that carry their
own approval); there is no silent pass.
"""


class GateRejected(Exception):
    """Raised when the gate cannot or will not approve."""


def approve(text: str, auto_approve: bool = False, input_fn=input) -> bool:
    """Return True only on an explicit human yes (or explicit opt-in)."""
    if auto_approve:
        return True
    print("\n--- completion awaiting approval ---")
    print(text)
    print("--- approve? [y/N] ---")
    try:
        answer = input_fn("> ").strip().lower()
    except EOFError as exc:
        raise GateRejected("no interactive input available; gate stays closed") from exc
    return answer in ("y", "yes")
