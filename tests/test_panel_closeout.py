"""Panel close-out enforcement (his order 2026-11-24): a panel
reports COMPLETE only when every claimed seat has an approved
ticket and a bound verdict text; otherwise PARTIAL or
NOT CONVENED, in those words."""
import json
import os
import tempfile
import unittest

from gated_dispatch import panel_closeout


def _write(path, obj, lines=False):
    with open(path, "w", encoding="utf-8") as fh:
        if lines:
            for row in obj:
                fh.write(json.dumps(row) + "\n")
        else:
            json.dump(obj, fh)


def _ticket(tid, provider="anthropic", model="m", status="approved",
            cost=0.01, source="list"):
    return {"ticket": tid, "provider": provider, "model": model,
            "status": status, "tokens_in": 100, "tokens_out": 200,
            "cost_usd": cost, "cost_source": source,
            "ts": "2026-11-24T00:00:00+00:00"}


class TestPanelCloseout(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp()
        self.ledger = os.path.join(self.dir, "panel.jsonl")
        self.verdicts = os.path.join(self.dir, "verdicts.json")

    def test_complete_panel(self):
        _write(self.ledger, [_ticket("T1"), _ticket("T2")], lines=True)
        _write(self.verdicts, {
            "claude": {"ticket": "T1", "text": "VERDICT ... concur"},
            "gemini": {"ticket": "T2", "text": "VERDICT ... concur"}})
        r = panel_closeout.closeout("p", self.ledger,
                                    ["claude", "gemini"], self.verdicts)
        self.assertEqual(r["status"], "COMPLETE")
        self.assertTrue(r["complete"])
        self.assertEqual(r["total_cost_usd_recorded_basis"], 0.02)
        self.assertIn("Cost (recorded basis)", r["markdown"])

    def test_missing_seat_reports_partial(self):
        _write(self.ledger, [_ticket("T1")], lines=True)
        _write(self.verdicts, {
            "claude": {"ticket": "T1", "text": "VERDICT ..."},
            "gemini": {"ticket": "T9", "text": "VERDICT ..."}})
        r = panel_closeout.closeout("p", self.ledger,
                                    ["claude", "gemini"], self.verdicts)
        self.assertEqual(r["status"], "PARTIAL")
        self.assertFalse(r["complete"])
        self.assertEqual(r["missing_seats"], ["gemini"])
        self.assertIn("PARTIAL", r["markdown"])

    def test_ticket_without_verdict_text_is_missing(self):
        _write(self.ledger, [_ticket("T1"), _ticket("T2")], lines=True)
        _write(self.verdicts, {
            "claude": {"ticket": "T1", "text": "VERDICT ..."},
            "gemini": {"ticket": "T2", "text": ""}})
        r = panel_closeout.closeout("p", self.ledger,
                                    ["claude", "gemini"], self.verdicts)
        self.assertEqual(r["status"], "PARTIAL")
        self.assertEqual(r["missing_seats"], ["gemini"])

    def test_no_approved_tickets_not_convened(self):
        _write(self.ledger, [_ticket("T1", status="blocked-router:x")],
               lines=True)
        _write(self.verdicts, {})
        r = panel_closeout.closeout("p", self.ledger,
                                    ["claude"], self.verdicts)
        self.assertEqual(r["status"], "NOT CONVENED")
        self.assertFalse(r["complete"])

    def test_mixed_basis_named_on_face(self):
        _write(self.ledger, [
            _ticket("T1", source="grant-offset"),
            _ticket("T2", provider="openrouter", source="provider-cost",
                    cost=0.0)], lines=True)
        _write(self.verdicts, {
            "claude": {"ticket": "T1", "text": "VERDICT ..."},
            "openai": {"ticket": "T2", "text": "VERDICT ..."}})
        r = panel_closeout.closeout("p", self.ledger,
                                    ["claude", "openai"], self.verdicts)
        self.assertTrue(r["mixed_basis"])
        self.assertIn("mixed cost bases", r["markdown"])


if __name__ == "__main__":
    unittest.main()
