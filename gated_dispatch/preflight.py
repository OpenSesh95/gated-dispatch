"""TS-PRE preflight contract (C-029 Group A, H-A1).

No scored run fires until a preflight record proves, per leg,
before firing:

  (i)   the named seat serves as itself — one gated proof dispatch
        whose served model equals the resolved (fired) model;
  (ii)  the named class resolves to the intended seat — a dry
        resolve against the live throttle state lands on the
        leg's declared expect_fires seat;
  (iii) seat_mode is declared on the record.

Cheap checks run first; the proof dispatch (lane-check cost)
fires only for legs that pass them. Any failed leg blocks the
run: verdict BLOCKED, and nothing the run later produces scores
against a missing or blocked preflight record. The record is
the contract.
"""

from __future__ import annotations

import json
import time
from datetime import datetime, timezone

from . import certs as certs_mod
from . import cli as cli_mod
from . import prompts as prompts_mod
from . import throttle as throttle_mod

PROOF_PROMPT = "Reply with exactly: lane live"


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def preflight(legs: list[dict], ledger_path: str,
              throttle_state_path: str | None = None,
              transport=None, time_fn=time.time,
              certs_path: str | None = None,
              drifted: set[str] | None = None) -> dict:
    """Run the TS-PRE checks for a roster of legs.

    Each leg: {leg, model, provider, loop_class, seat_mode,
    expect_fires (optional, defaults to model)}.
    Returns the preflight record; record["verdict"] is PASS only
    when every leg passes every check.
    """
    state = throttle_mod.ThrottleState(
        throttle_state_path
        or cli_mod._default_sidecar(ledger_path, ".throttle.json")
    )
    out_legs = []
    verdict = "PASS"
    for leg in legs:
        model = leg["model"]
        loop_class = leg.get("loop_class", "panel")
        seat_mode = leg.get("seat_mode")
        expect = leg.get("expect_fires", model)
        checks = {"seat_mode_declared": False, "resolves": False,
                  "serves": False}
        detail = {}
        # TS-PROMPT (C-039): a scored leg must carry a complete prompt
        # stamp — every declared prompt text must hash to a registered
        # registry version. A scored leg without one reads UNMEASURED
        # and the preflight names it rather than passing it silently.
        if leg.get("scored"):
            checks["prompt_stamp"] = False
            registry = leg.get("prompt_registry")
            texts = leg.get("prompt_texts") or {}
            if registry and texts:
                resolved_records = []
                ok = True
                for species, text in texts.items():
                    record = prompts_mod.verify_text(registry, text)
                    if record is None or record["species"] != species:
                        ok = False
                        detail["prompt_stamp"] = (
                            f"{species} prompt hash is unregistered "
                            "(TS-SEC provenance anomaly shape)")
                        break
                    resolved_records.append(record)
                if ok:
                    checks["prompt_stamp"] = True
                    detail["prompt_stamp"] = prompts_mod.build_stamp(
                        resolved_records,
                        leg.get("temperature_class", "provider-default"))
            else:
                detail["prompt_stamp"] = (
                    "UNMEASURED — scored leg declares no prompt stamp")
        # H-B1: a leg naming a role must hold a current cert when
        # the engagement supplies a cert store. An uncertified
        # leg cannot be composed.
        if certs_path is not None and leg.get("role"):
            status = certs_mod.check_leg(
                certs_mod.load_certs(certs_path), model=model,
                role=leg["role"],
                set_version=leg.get("set_version", ""),
                drifted=drifted)["status"]
            checks["certified"] = status == "certified"
            if status != "certified":
                detail["cert"] = status
        # (iii) seat_mode declared
        if seat_mode in ("chain", "named"):
            checks["seat_mode_declared"] = True
        else:
            detail["seat_mode"] = f"undeclared or invalid: {seat_mode!r}"
        # (ii) dry resolve against the live state
        resolved = None
        if checks["seat_mode_declared"]:
            try:
                res = throttle_mod.resolve(
                    loop_class, model, state, time_fn(),
                    seat_mode=seat_mode)
                resolved = res.model
                if resolved == expect:
                    checks["resolves"] = True
                else:
                    detail["resolve"] = (
                        f"resolves to {resolved}, leg expects {expect}")
            except Exception as exc:  # banned, breached, quarantined
                detail["resolve"] = f"{type(exc).__name__}: {exc}"
        # (i) gated proof — only for legs passing the cheap checks
        ticket = None
        if (checks["seat_mode_declared"] and checks["resolves"]
                and checks.get("certified", True)):
            row = cli_mod.run(
                PROOF_PROMPT, model, ledger_path=ledger_path,
                provider=leg.get("provider", "google"),
                loop_class=loop_class, seat_mode=seat_mode,
                auto_approve=True, transport=transport)
            ticket = row["ticket"]
            served_ok = (
                row["status"] == "approved"
                and row["model"] == resolved
                and row.get("model_match") is True
            )
            checks["serves"] = served_ok
            if not served_ok:
                detail["serves"] = (
                    f"status={row['status']} fired={row['model']} "
                    f"model_match={row.get('model_match')}")
        leg_status = "PASS" if all(checks.values()) else "FAIL"
        if leg_status == "FAIL":
            verdict = "BLOCKED"
        out_legs.append({
            "leg": leg.get("leg", model),
            "model": model,
            "loop_class": loop_class,
            "seat_mode": seat_mode,
            "expect_fires": expect,
            "resolved": resolved,
            "checks": checks,
            "detail": detail,
            "proof_ticket": ticket,
            "status": leg_status,
        })
    return {"ts": _now_iso(), "set": "TS-PRE", "legs": out_legs,
            "verdict": verdict}


def main(argv=None) -> int:
    import argparse
    parser = argparse.ArgumentParser(prog="gated_dispatch.preflight")
    parser.add_argument("legs_file",
                        help="JSON file: a list of leg objects")
    parser.add_argument("--ledger", default="preflight.jsonl")
    parser.add_argument("--record",
                        help="append the record to this JSONL file")
    args = parser.parse_args(argv)
    with open(args.legs_file, encoding="utf-8") as fh:
        legs = json.load(fh)
    record = preflight(legs, ledger_path=args.ledger)
    if args.record:
        with open(args.record, "a", encoding="utf-8") as fh:
            fh.write(json.dumps(record, sort_keys=True) + "\n")
    print(json.dumps(record, indent=1, sort_keys=True))
    return 0 if record["verdict"] == "PASS" else 3


if __name__ == "__main__":
    raise SystemExit(main())
