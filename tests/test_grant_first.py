"""Grant-first booking (his ruling 2026-11-17; gate v0.4.30).

An Anthropic ticket covered by the prepaid credit books
cost_source "grant-offset", never cash; the envelope math keeps
grant draw out of the cash totals; an exhausted credit flips
booking back to "list"; a corrupt register blocks before dispatch.
"""

import json
import os
import tempfile
import unittest
from datetime import datetime, timezone

from gated_dispatch import cli, envelopes, grants


def anthropic_raw(text="lane live", model="claude-haiku-5-5",
                  tin=19, tout=5):
    return {
        "model": model,
        "content": [{"type": "text", "text": text}],
        "usage": {"input_tokens": tin, "output_tokens": tout},
    }


def _register(tmp, remaining, seeded_at="2026-11-17T00:00:00+00:00"):
    path = os.path.join(tmp, "grant-register.json")
    data = {"version": 1, "grants": [{
        "provider": "anthropic", "kind": "prepaid-credit-purchase",
        "granted_on": "2026-11-11", "amount_usd": 30.0, "tax_usd": 1.98,
        "drawn_at_seed_usd": round(30.0 - remaining, 6),
        "remaining_at_seed_usd": remaining,
        "seeded_at": seeded_at, "expires_on": "2027-11-12",
    }]}
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(data, fh)
    return path


class GrantFirstTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.ledger = os.path.join(self.tmp.name, "ledger.jsonl")
        self._old_env = os.environ.get("GD_GRANT_REGISTER")

    def tearDown(self):
        if self._old_env is None:
            os.environ.pop("GD_GRANT_REGISTER", None)
        else:
            os.environ["GD_GRANT_REGISTER"] = self._old_env
        self.tmp.cleanup()

    def _run_haiku(self):
        return cli.run(
            "Reply with exactly: lane live", "claude-haiku-5-5",
            ledger_path=self.ledger, provider="anthropic",
            envelope="frontier", auto_approve=True,
            loop_class="lower-order",
            transport=lambda m, p: anthropic_raw())

    def _feed_final(self):
        path = os.path.splitext(self.ledger)[0] + ".dispatch.jsonl"
        recs = [json.loads(x) for x in open(path) if x.strip()]
        return [r for r in recs if r.get("run_outcome")][-1]

    def test_covered_ticket_books_grant_offset(self):
        os.environ["GD_GRANT_REGISTER"] = _register(self.tmp.name, 10.0)
        row = self._run_haiku()
        self.assertEqual(row["status"], "approved")
        self.assertEqual(row["cost_source"], "grant-offset")
        self.assertEqual(row["checks"]["grant"]["remaining_before_usd"],
                         10.0)
        self.assertFalse(row["checks"]["grant"]["straddle"])
        final = self._feed_final()
        self.assertEqual(final["cost_source"], "grant-offset")
        self.assertEqual(final["grant"]["remaining_before_usd"], 10.0)

    def test_draw_decrements_remaining(self):
        os.environ["GD_GRANT_REGISTER"] = _register(self.tmp.name, 10.0)
        first = self._run_haiku()
        second = self._run_haiku()
        self.assertEqual(second["cost_source"], "grant-offset")
        self.assertAlmostEqual(
            second["checks"]["grant"]["remaining_before_usd"],
            10.0 - first["cost_usd"], places=6)

    def test_exhausted_credit_books_list(self):
        os.environ["GD_GRANT_REGISTER"] = _register(self.tmp.name, 0.0)
        row = self._run_haiku()
        self.assertEqual(row["status"], "approved")
        self.assertEqual(row["cost_source"], "list")
        self.assertNotIn("grant", row["checks"])

    def test_straddle_flag_on_boundary_cross(self):
        # Haiku stub cost is ~3.1e-06; a remaining of 1e-06 crosses.
        os.environ["GD_GRANT_REGISTER"] = _register(self.tmp.name, 0.000001)
        row = self._run_haiku()
        self.assertEqual(row["cost_source"], "grant-offset")
        self.assertTrue(row["checks"]["grant"]["straddle"])

    def test_corrupt_register_blocks_before_dispatch(self):
        path = os.path.join(self.tmp.name, "grant-register.json")
        with open(path, "w", encoding="utf-8") as fh:
            fh.write("{not json")
        os.environ["GD_GRANT_REGISTER"] = path

        def boom(m, p):
            raise AssertionError("transport must not fire on a block")

        row = cli.run(
            "Reply with exactly: lane live", "claude-haiku-5-5",
            ledger_path=self.ledger, provider="anthropic",
            envelope="frontier", auto_approve=True,
            loop_class="lower-order", transport=boom)
        self.assertEqual(row["status"], "blocked-grant:register")

    def test_no_register_is_inert(self):
        os.environ["GD_GRANT_REGISTER"] = os.path.join(
            self.tmp.name, "absent.json")
        row = self._run_haiku()
        self.assertEqual(row["status"], "approved")
        self.assertEqual(row["cost_source"], "list")

    def test_mtd_buckets_grant_apart_from_cash(self):
        month = datetime.now(timezone.utc).strftime("%Y-%m")
        rows = [
            {"ts": month + "-05T00:00:00+00:00", "provider": "anthropic",
             "cost_usd": 2.0, "cost_source": "grant-offset",
             "envelope": "frontier", "lane": "anthropic"},
            {"ts": month + "-05T00:01:00+00:00", "provider": "anthropic",
             "cost_usd": 3.0, "cost_source": "list",
             "envelope": "frontier", "lane": "anthropic"},
            {"ts": month + "-05T00:02:00+00:00", "provider": "google",
             "cost_usd": 1.5, "envelope": "frontier", "lane": "google"},
        ]
        with open(self.ledger, "w", encoding="utf-8") as fh:
            for r in rows:
                fh.write(json.dumps(r) + "\n")
        mtd = envelopes.month_to_date(self.ledger)
        self.assertEqual(mtd["total"], 4.5)
        self.assertEqual(mtd["grant"], 2.0)
        self.assertEqual(mtd["envelopes"]["frontier"], 4.5)


if __name__ == "__main__":
    unittest.main()
