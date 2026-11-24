"""Panel close-out: a panel cannot close or report without a
ticket per claimed seat.

His order 2026-11-24 (via CoS): through the Council, ALL
frontiers actually weigh in — enforced by the machinery, not
by assurance. This module is the enforcement point:

- closeout() reads the panel's OWN ledger (the STD-0 tickets
  the gate wrote at dispatch time) and the runner's verdict
  capture, and cross-checks every CLAIMED seat: exactly one
  approved ticket carrying api_usage tokens and a cost with
  its basis (cost_source), plus a verdict text bound to that
  ticket.
- The report is GENERATED from those tickets — per-seat
  tokens, dollar cost, and the basis named on its face. A
  seat that did not return is not narrated in: the panel
  reports PARTIAL (naming the missing seats) or NOT CONVENED
  (no approved tickets at all), in those words.
- complete is True only when every claimed seat checks out.
  Callers must not report a panel as closed on a closeout
  whose complete is False.

Cost basis: each ticket's cost_source is printed beside its
cost; when the seats of one panel carry different bases, the
report says so on its face (the 2026-11-24 basis correction:
lane-recorded totals are not list-value totals).
"""
import hashlib
import json
import os


def _load_ledger(ledger_path):
    rows = []
    if os.path.exists(ledger_path):
        for line in open(ledger_path, encoding="utf-8"):
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    return rows


def _load_verdicts(verdicts_path):
    if verdicts_path and os.path.exists(verdicts_path):
        with open(verdicts_path, encoding="utf-8") as fh:
            return json.load(fh)
    return {}


def closeout(panel_name, ledger_path, claimed_seats, verdicts_path=None):
    """claimed_seats: list of seat keys as they appear in the
    verdict capture (e.g. ["claude", "gemini", "grok",
    "openai"]). Returns (report_dict, markdown)."""
    tickets = _load_ledger(ledger_path)
    verdicts = _load_verdicts(verdicts_path)
    approved = [t for t in tickets if t.get("status") == "approved"]

    seats = {}
    missing = []
    for seat in claimed_seats:
        v = verdicts.get(seat) or {}
        ticket_id = v.get("ticket")
        match = [t for t in approved if t.get("ticket") == ticket_id]
        text = v.get("text") or ""
        if match and text:
            t = match[0]
            seats[seat] = {
                "ticket": t["ticket"],
                "provider": t["provider"],
                "model": t["model"],
                "tokens_in": t["tokens_in"],
                "tokens_out": t["tokens_out"],
                "cost_usd": t["cost_usd"],
                "cost_source": t.get("cost_source", "not-recorded"),
                "verdict_chars": len(text),
                "verdict_sha256": hashlib.sha256(
                    text.encode("utf-8")).hexdigest()[:16],
            }
        else:
            missing.append(seat)

    if not approved:
        status = "NOT CONVENED"
    elif missing:
        status = "PARTIAL"
    else:
        status = "COMPLETE"

    bases = sorted({s["cost_source"] for s in seats.values()})
    total = round(sum(s["cost_usd"] for s in seats.values()), 6)
    report = {
        "panel": panel_name,
        "status": status,
        "complete": status == "COMPLETE",
        "claimed_seats": list(claimed_seats),
        "seats": seats,
        "missing_seats": missing,
        "total_cost_usd_recorded_basis": total,
        "cost_bases": bases,
        "mixed_basis": len(bases) > 1,
        "tickets_in_ledger": len(tickets),
        "approved_tickets": len(approved),
    }

    lines = [f"PANEL REPORT — {panel_name} (generated from tickets)",
             f"Status: {status}"]
    for seat in claimed_seats:
        if seat in seats:
            s = seats[seat]
            lines.append(
                f"- {seat}: ticket {s['ticket']} · "
                f"{s['provider']}/{s['model']} · "
                f"in {s['tokens_in']} · out {s['tokens_out']} · "
                f"${s['cost_usd']:.6f} (basis: {s['cost_source']}) · "
                f"verdict {s['verdict_chars']} chars "
                f"(sha {s['verdict_sha256']})")
        else:
            lines.append(f"- {seat}: NO APPROVED TICKET / NO VERDICT "
                         f"ON RECORD — not counted")
    lines.append(f"Cost (recorded basis): ${total:.6f} across "
                 f"{len(seats)} seats · bases: {', '.join(bases)}")
    if report["mixed_basis"]:
        lines.append("NOTE: mixed cost bases across seats — the "
                     "total is a lane-recorded total, not a "
                     "uniform list-value total.")
    if missing:
        lines.append(f"Missing seats: {', '.join(missing)} — this "
                     f"panel reports as {status}, in those words.")
    report["markdown"] = "\n".join(lines)
    return report
