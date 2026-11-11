"""STD-0 tests: lane parsers, ticket completeness, envelope stops.

Run: python -m unittest discover -s tests -v
"""

import json
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from gated_dispatch import cli, envelopes, lanes  # noqa: E402


def anthropic_raw(text="lane live", model="claude-haiku-5-5", tin=19, tout=5):
    return {
        "model": model,
        "content": [{"type": "text", "text": text}],
        "usage": {"input_tokens": tin, "output_tokens": tout},
    }


def gemini_raw(text="lane live", model="gemini-3.8-flash", pin=11, cand=3, thoughts=2):
    return {
        "modelVersion": model,
        "candidates": [{"content": {"parts": [{"text": text}]}}],
        "usageMetadata": {
            "promptTokenCount": pin,
            "candidatesTokenCount": cand,
            "thoughtsTokenCount": thoughts,
            "totalTokenCount": pin + cand + thoughts,
        },
    }


def xai_raw(text="lane live", model="grok-4.20-0309-non-reasoning", tin=14, tout=4):
    return {
        "model": model,
        "choices": [{"message": {"content": text}}],
        "usage": {"prompt_tokens": tin, "completion_tokens": tout},
    }


class ParserTest(unittest.TestCase):
    def test_anthropic_usage_fields(self):
        c = lanes.parse_anthropic(anthropic_raw())
        self.assertEqual((c.tokens_in, c.tokens_out), (19, 5))
        self.assertEqual(c.model_served, "claude-haiku-5-5")

    def test_gemini_thinking_tokens_bill_as_output(self):
        c = lanes.parse_gemini(gemini_raw())
        self.assertEqual(c.tokens_in, 11)
        self.assertEqual(c.tokens_out, 5)  # 3 candidates + 2 thinking

    def test_openai_shape(self):
        c = lanes.parse_openai(xai_raw())
        self.assertEqual((c.tokens_in, c.tokens_out), (14, 4))


class TicketTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.ledger = os.path.join(self.tmp.name, "ledger.jsonl")

    def tearDown(self):
        self.tmp.cleanup()

    def test_ticket_is_complete(self):
        row = cli.run(
            "Reply with exactly: lane live",
            "claude-haiku-5-5",
            ledger_path=self.ledger,
            provider="anthropic",
            envelope="frontier",
            required_terms=("lane live",),
            auto_approve=True,
            transport=lambda m, p: anthropic_raw(),
        )
        self.assertEqual(row["status"], "approved")
        self.assertEqual(row["tokens_source"], "api_usage")
        self.assertTrue(row["model_match"])
        self.assertEqual(row["envelope"], "frontier")
        self.assertEqual(row["lane"], "anthropic")
        self.assertGreater(row["cost_usd"], 0)
        self.assertEqual(row["owner_minute_rate_usd"], 2.00)
        for field in ("ticket", "provider", "model_served", "envelope_mtd_usd",
                      "lane_mtd_usd", "backstop_mtd_usd", "owner_minutes"):
            self.assertIn(field, row)

    def test_unmetered_model_stops_before_dispatch(self):
        called = []

        def transport(m, p):
            called.append(True)
            return anthropic_raw()

        row = cli.run(
            "anything", "claude-opus-9-9", ledger_path=self.ledger,
            provider="anthropic", auto_approve=True, transport=transport,
        )
        self.assertEqual(row["status"], "blocked-unmetered")
        self.assertEqual(called, [])

    def test_alias_drift_is_flagged_not_hidden(self):
        row = cli.run(
            "Reply with exactly: lane live",
            "claude-haiku-5-5",
            ledger_path=self.ledger,
            provider="anthropic",
            required_terms=("lane live",),
            auto_approve=True,
            transport=lambda m, p: anthropic_raw(model="claude-sonnet-5-5"),
        )
        self.assertEqual(row["status"], "approved")
        self.assertFalse(row["model_match"])
        self.assertEqual(row["model_served"], "claude-sonnet-5-5")

    def test_envelope_exhaustion_blocks(self):
        # Seed the frontier envelope past its cap with a synthetic row.
        seed = {
            "ts": "2999-01-01T00:00:00+00:00", "cost_usd": 0.0,
        }
        # month_to_date reads the current month; write a current-month row.
        from datetime import datetime, timezone

        now = datetime.now(timezone.utc).isoformat(timespec="seconds")
        with open(self.ledger, "w", encoding="utf-8") as fh:
            fh.write(json.dumps({
                "ts": now, "cost_usd": envelopes.ENVELOPES_USD["frontier"],
                "envelope": "frontier", "lane": "anthropic",
            }) + "\n")
        row = cli.run(
            "anything", "claude-haiku-5-5", ledger_path=self.ledger,
            provider="anthropic", auto_approve=True,
            transport=lambda m, p: anthropic_raw(),
        )
        self.assertTrue(row["status"].startswith("blocked-envelope"))

    def test_owner_minutes_clamped(self):
        answers = iter(["y"])
        row = cli.run(
            "Reply with exactly: lane live",
            "claude-haiku-5-5",
            ledger_path=self.ledger,
            provider="anthropic",
            required_terms=("lane live",),
            auto_approve=False,
            transport=lambda m, p: anthropic_raw(),
            input_fn=lambda prompt="": next(answers),
        )
        self.assertEqual(row["status"], "approved")
        self.assertGreaterEqual(row["owner_minutes"], 0.0)
        self.assertLessEqual(row["owner_minutes"], cli.OWNER_MINUTE_CLAMP)
        self.assertIn("shown", row["gate"])


if __name__ == "__main__":
    unittest.main()
