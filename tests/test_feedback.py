import json
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from gated_dispatch import feedback  # noqa: E402


class TestFeedback(unittest.TestCase):
    def setUp(self):
        fd, self.feed = tempfile.mkstemp(suffix=".jsonl")
        os.close(fd)
        os.unlink(self.feed)
        self.kw = dict(ticket_ref="GD-20261115-0001", prompt_id="bench1-sc1-extract",
                       routing_class="qr-research", lane="google",
                       model="gemini-3.6-flash")

    def rows(self):
        if not os.path.exists(self.feed):
            return []
        with open(self.feed, encoding="utf-8") as fh:
            return [json.loads(x) for x in fh if x.strip()]

    def test_lexicon_is_the_fixed_four(self):
        self.assertEqual(feedback.LEXICON, {
            "\U0001F44D": "satisfied", "\U0001F44E": "failed",
            "\U0001F501": "rework", "\U0001F31F": "exceptional"})

    def test_explicit_satisfied(self):
        row = feedback.record_feedback(self.feed, emoji="\U0001F44D", **self.kw)
        self.assertEqual(row["signal"], "satisfied")
        self.assertEqual(row["outcome_kind"], "accepted")
        self.assertEqual(row["signal_weight"], 1.0)
        self.assertEqual(row["feedback_source"], "user")
        self.assertEqual(row["query_class"], "qr-research")
        self.assertEqual(row["route_taken"], "google/gemini-3.6-flash")
        self.assertEqual(self.rows(), [row])

    def test_exceptional_flags_the_row(self):
        row = feedback.record_feedback(self.feed, emoji="\U0001F31F", **self.kw)
        self.assertEqual(row["signal"], "exceptional")
        self.assertTrue(row["exceptional"])
        self.assertEqual(row["outcome_kind"], "accepted")

    def test_rework_maps_to_corrected(self):
        row = feedback.record_feedback(self.feed, emoji="\U0001F501", **self.kw)
        self.assertEqual(row["outcome_kind"], "corrected")

    def test_unknown_emoji_rejected_writes_nothing(self):
        with self.assertRaises(ValueError):
            feedback.record_feedback(self.feed, emoji="\U0001F525", **self.kw)
        self.assertEqual(self.rows(), [])

    def test_inferred_path_weighs_less(self):
        row = feedback.record_feedback(self.feed, signal="rework",
                                       source="inferred", **self.kw)
        self.assertEqual(row["signal_weight"], 0.5)
        self.assertEqual(row["signal_origin"], "inferred")

    def test_silence_writes_no_row(self):
        # There is no silence API; an unreacted output simply never
        # calls record_feedback. The feed stays absent/empty.
        self.assertEqual(self.rows(), [])


if __name__ == "__main__":
    unittest.main()
