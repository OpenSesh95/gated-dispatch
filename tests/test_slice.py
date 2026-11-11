"""Offline tests for the full slice, using a stub transport.

Run: python -m unittest discover -s tests -v
"""

import json
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from gated_dispatch import cli  # noqa: E402


def stub_transport(text, tokens_in=120, tokens_out=45):
    def _transport(model, prompt):
        return {
            "model": model,
            "choices": [{"message": {"content": text}}],
            "usage": {"prompt_tokens": tokens_in, "completion_tokens": tokens_out},
        }

    return _transport


class SliceTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.ledger = os.path.join(self.tmp.name, "ledger.jsonl")

    def tearDown(self):
        self.tmp.cleanup()

    def rows(self):
        with open(self.ledger, encoding="utf-8") as fh:
            return [json.loads(line) for line in fh]

    def test_happy_path_approved_and_metered(self):
        row = cli.run(
            "Summarize the change log.",
            "gpt-5-mini",
            ledger_path=self.ledger,
            required_terms=("change",),
            auto_approve=True,
            transport=stub_transport("The change log lists two fixes."),
        )
        self.assertEqual(row["status"], "approved")
        self.assertGreater(row["cost_usd"], 0)
        self.assertEqual(len(row["prompt_sha256"]), 64)
        self.assertEqual(len(self.rows()), 1)

    def test_verification_failure_never_reaches_gate(self):
        row = cli.run(
            "Write the summary.",
            "gpt-5-mini",
            ledger_path=self.ledger,
            required_terms=("quarterly",),
            auto_approve=True,
            transport=stub_transport("A short summary."),
        )
        self.assertEqual(row["status"], "rejected-verification")
        self.assertFalse(row["checks"]["contains:quarterly"])

    def test_gate_rejection_is_recorded(self):
        row = cli.run(
            "Write the summary.",
            "gpt-5-mini",
            ledger_path=self.ledger,
            auto_approve=False,
            transport=stub_transport("A short summary."),
        )
        self.assertEqual(row["status"], "rejected-gate")

    def test_provider_error_is_recorded(self):
        def boom(model, prompt):
            raise ConnectionError("provider unreachable")

        row = cli.run(
            "Anything.",
            "gpt-5-mini",
            ledger_path=self.ledger,
            auto_approve=True,
            transport=boom,
        )
        self.assertEqual(row["status"], "error:ConnectionError")
        self.assertEqual(row["cost_usd"], 0.0)


if __name__ == "__main__":
    unittest.main()
