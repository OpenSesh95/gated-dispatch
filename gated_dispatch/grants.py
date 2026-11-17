"""Grant-first booking (his ruling 2026-11-17 10:59 CT).

Prepaid credit exists in his Anthropic account (console read
2026-11-17: a $30 credit purchase of 2026-11-11, $1.61 used at seed,
balance $28.39, expires 2027-11-12). Draw order: credit burns before
billed spend. A dispatch covered by the credit balance books
cost_source "grant-offset", never cash ("list"); when the credit is
exhausted, booking flips back to the static source.

The register is machine state at the gate tree root
(grant-register.json, or the file GD_GRANT_REGISTER names): one
active grant per provider in v1, seeded from a console read — the
gate never invents the opening position. Remaining at any moment =
remaining_at_seed minus the grant-offset tickets booked on that
provider since seeded_at, read from the run's own ledger.

Straddle rule (v1): a ticket that crosses the boundary books
whole-ticket grant-offset and carries straddle=true for FinOps
reconciliation (the schema holds one cost_source per ticket).

Failure modes: no register file = the seam is inert (pre-grant
behavior). A register that exists but cannot be parsed raises
GrantError; cli.run blocks the ticket as blocked-grant:register
before dispatch — booking correctness is never silently dropped.
"""

import json
import os
from datetime import datetime, timezone

_DEFAULT_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "grant-register.json")


class GrantError(Exception):
    pass


def register_path() -> str:
    return os.environ.get("GD_GRANT_REGISTER") or _DEFAULT_PATH


def load_register(path: str | None = None) -> dict | None:
    """The parsed register, or None when no register file exists."""
    path = path or register_path()
    if not os.path.exists(path):
        return None
    try:
        with open(path, encoding="utf-8") as fh:
            data = json.load(fh)
        for g in data["grants"]:
            float(g["remaining_at_seed_usd"])
            datetime.fromisoformat(g["seeded_at"])
            if g.get("expires_on"):
                datetime.fromisoformat(g["expires_on"])
        return data
    except Exception as exc:
        raise GrantError(f"grant register unreadable: {exc}") from exc


def active_grant(register: dict, provider: str,
                 now: datetime | None = None) -> dict | None:
    now = now or datetime.now(timezone.utc)
    for g in register.get("grants", []):
        if g.get("provider") != provider:
            continue
        exp = g.get("expires_on")
        if exp and datetime.fromisoformat(exp).date() < now.date():
            continue
        return g
    return None


def drawn_since(grant: dict, ledger_path: str) -> float:
    """Grant-offset draw booked on this provider since the seed."""
    seeded = datetime.fromisoformat(grant["seeded_at"])
    total = 0.0
    if not os.path.exists(ledger_path):
        return 0.0
    with open(ledger_path, encoding="utf-8") as fh:
        for line in fh:
            try:
                row = json.loads(line)
            except ValueError:
                continue
            if row.get("provider") != grant["provider"]:
                continue
            if row.get("cost_source") != "grant-offset":
                continue
            ts = row.get("ts")
            if ts and datetime.fromisoformat(ts) >= seeded:
                total += float(row.get("cost_usd", 0) or 0)
    return round(total, 6)


def remaining(grant: dict, ledger_path: str) -> float:
    return round(float(grant["remaining_at_seed_usd"])
                 - drawn_since(grant, ledger_path), 6)


def decide(register: dict | None, provider: str, ledger_path: str,
           cost_usd: float) -> dict | None:
    """The booking stamp for one completed ticket, or None when
    grant-first does not apply (no register, no active grant for the
    provider, or the credit is exhausted — the caller then books its
    static source)."""
    if register is None:
        return None
    grant = active_grant(register, provider)
    if grant is None:
        return None
    rem = remaining(grant, ledger_path)
    if rem <= 0:
        return None
    return {
        "cost_source": "grant-offset",
        "grant_provider": provider,
        "remaining_before_usd": rem,
        "straddle": bool(cost_usd > rem),
        "expires_on": grant.get("expires_on"),
    }
