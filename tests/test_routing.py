"""Routing Table v0 tests: chokepoint admission, TEST-0, B7, stamps.

Run: python -m unittest tests.test_routing -v
"""

import json
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from gated_dispatch import cli, routing  # noqa: E402


def xai_raw(text="lane live", model="grok-4.20-0309-non-reasoning",
            tin=14, tout=4):
    return {
        "model": model,
        "choices": [{"message": {"content": text}}],
        "usage": {"prompt_tokens": tin, "completion_tokens": tout},
    }


def boom_transport(m, p):
    raise AssertionError("transport must not be called on a refusal")


class ResolveTest(unittest.TestCase):
    def test_panel_chain_head_admitted(self):
        d = routing.resolve("qr-panel-verdict", "google", "gemini-3.6-flash")
        self.assertTrue(d.allowed)
        self.assertEqual(d.stamp["position"], "chain-0")
        self.assertEqual(d.stamp["table_version"], "v0")
        self.assertEqual(d.stamp["table_hash"], routing.TABLE_HASH)

    def test_flagship_admitted_where_row_says_so(self):
        d = routing.resolve("qr-canon-drafting", "anthropic",
                            "claude-opus-5-5")
        self.assertTrue(d.allowed)
        self.assertEqual(d.stamp["position"], "flagship")

    def test_class_mismatch_refused(self):
        d = routing.resolve("qr-canon-drafting", "anthropic",
                            "claude-haiku-5-5")
        self.assertFalse(d.allowed)
        self.assertEqual(d.cause, "class-mismatch")

    def test_commission_ruling_is_flagship_only(self):
        d = routing.resolve("qr-commission-ruling", "anthropic",
                            "claude-sonnet-5-5")
        self.assertFalse(d.allowed)
        d = routing.resolve("qr-commission-ruling", "anthropic",
                            "claude-opus-5-5")
        self.assertTrue(d.allowed)

    def test_geneva_direct_refuses_frontier(self):
        d = routing.resolve("qr-life-ops", "google", "gemini-3.6-flash")
        self.assertFalse(d.allowed)
        self.assertEqual(d.cause, "geneva-direct")

    def test_local_admitted_on_any_class(self):
        d = routing.resolve("qr-research", "gcp", "qwen3:14b")
        self.assertTrue(d.allowed)
        self.assertEqual(d.stamp["position"], "local")

    def test_test0_fails_closed(self):
        d = routing.resolve("qr-research", "google", "gemini-3.6-flash",
                            local_only=True)
        self.assertFalse(d.allowed)
        self.assertEqual(d.cause, "test-0")
        d = routing.resolve("qr-research", "local", "llama3.1:8b",
                            local_only=True)
        self.assertTrue(d.allowed)

    def test_b7_bypass(self):
        d = routing.resolve("ad-hoc", "anthropic", "claude-opus-5-5")
        self.assertFalse(d.allowed)
        self.assertEqual(d.cause, "b7-bypass")
        d = routing.resolve("ad-hoc", "local", "llama3.1:8b")
        self.assertTrue(d.allowed)
        self.assertEqual(d.stamp["class"], "b7-bypass")

    def test_combination_needs_dominant(self):
        d = routing.resolve("qr-combination", "google", "gemini-3.6-flash")
        self.assertFalse(d.allowed)
        self.assertEqual(d.cause, "combination-needs-dominant")
        d = routing.resolve("qr-combination", "google", "gemini-3.6-flash",
                            dominant="qr-research")
        self.assertTrue(d.allowed)
        self.assertEqual(d.stamp["class"], "qr-research")
        self.assertEqual(d.stamp["composed_from"], "qr-combination")

    def test_unknown_class_falls_back_logged(self):
        d = routing.resolve("qr-nonsense", "google", "gemini-3.6-flash")
        self.assertFalse(d.allowed)  # fallback is Geneva-direct
        self.assertTrue(d.stamp["unclassified"])
        self.assertEqual(d.stamp["class"], "qr-quick-lookup")

    def test_select(self):
        self.assertEqual(routing.select("qr-research"),
                         ("google", "gemini-3.6-flash"))
        self.assertIsNone(routing.select("qr-quick-lookup"))
        self.assertEqual(
            routing.select("qr-combination", dominant="qr-live-wire"),
            ("xai", "grok-4.20-0309-non-reasoning"))

    def test_job_stamp_frontier_class(self):
        s = routing.job_stamp("qr-research")
        self.assertEqual(s["routing_class"], "qr-research")
        self.assertEqual(s["selected"], "google/gemini-3.6-flash")
        self.assertEqual(s["table_version"], "v0")

    def test_job_stamp_geneva_direct(self):
        s = routing.job_stamp("qr-career-ops")
        self.assertEqual(s["selected"], "geneva-direct")

    def test_job_stamp_flagship_only(self):
        s = routing.job_stamp("qr-commission-ruling")
        self.assertEqual(s["selected"],
                         "anthropic/claude-opus-5-5 (flagship)")

    def test_decomposition_stamp_combination(self):
        s = routing.decomposition_stamp("qr-combination",
                                        dominant="qr-research")
        self.assertEqual(s["routing_class"], "qr-research")
        self.assertEqual(s["routing_dominant"], "qr-research")
        self.assertEqual(s["composed_from"], "qr-combination")

    def test_nature_defaults_and_override(self):
        self.assertEqual(routing.resolve_nature("qr-panel-verdict"),
                         "algorithmic")
        self.assertEqual(routing.resolve_nature("qr-research"),
                         "probabilistic")
        self.assertEqual(routing.resolve_nature("qr-life-ops"),
                         "deterministic")
        self.assertEqual(
            routing.resolve_nature("qr-research", "algorithmic"),
            "algorithmic")
        with self.assertRaises(ValueError):
            routing.resolve_nature("qr-research", "quantum")

    def test_stamps_carry_nature_weight_hint(self):
        s = routing.job_stamp("qr-career-ops")
        self.assertEqual(s["nature"], "deterministic")
        self.assertEqual(s["weight"],
                         {"impact": "medium", "deliverables": 1})
        self.assertIn("plain compute", s["lane_hint"])
        d = routing.decomposition_stamp(
            "qr-coding-burst", weight={"impact": "high", "deliverables": 3})
        self.assertEqual(d["nature"], "algorithmic")
        self.assertEqual(d["weight"]["impact"], "high")
        self.assertIn("open-weight", d["lane_hint"])

    def test_manifest_test0_detection(self):
        m = {"data": {"sensitivity": "compartmented"}}
        self.assertTrue(routing.manifest_is_test0(m))
        m = {"data": {"sensitivity": "internal"}}
        self.assertFalse(routing.manifest_is_test0(m))
        self.assertFalse(routing.manifest_is_test0(None))


class RunIntegrationTest(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp()
        self.ledger = os.path.join(self.dir, "l.jsonl")

    def _final_dispatch_record(self):
        path = os.path.join(self.dir, "l.dispatch.jsonl")
        rows = [json.loads(x) for x in open(path) if x.strip()]
        return rows[-1]

    def test_routed_run_approved_and_stamped(self):
        row = cli.run(
            "Reply with exactly: lane live",
            "grok-4.20-0309-non-reasoning",
            ledger_path=self.ledger, provider="xai",
            envelope="frontier", required_terms=("lane live",),
            auto_approve=True, loop_class="lower-order",
            routing_class="qr-live-wire",
            transport=lambda m, p: xai_raw(),
        )
        self.assertEqual(row["status"], "approved")
        rec = self._final_dispatch_record()
        self.assertEqual(rec["routing"]["class"], "qr-live-wire")
        self.assertEqual(rec["routing"]["position"], "chain-0")
        self.assertEqual(rec["routing"]["table_version"], "v0")

    def test_routed_mismatch_blocked_before_dispatch(self):
        row = cli.run(
            "anything", "claude-haiku-5-5",
            ledger_path=self.ledger, provider="anthropic",
            envelope="frontier", auto_approve=True,
            routing_class="qr-canon-drafting",
            transport=boom_transport,
        )
        self.assertEqual(row["status"], "blocked-router:class-mismatch")

    def test_deterministic_nature_blocked_before_dispatch(self):
        row = cli.run(
            "anything", "claude-haiku-5-5",
            ledger_path=self.ledger, provider="anthropic",
            envelope="frontier", auto_approve=True,
            routing_class="qr-research", nature="deterministic",
            transport=boom_transport,
        )
        self.assertEqual(row["status"],
                         "blocked-router:nature-deterministic")

    def test_routed_run_stamp_carries_nature(self):
        row = cli.run(
            "Reply with exactly: lane live",
            "grok-4.20-0309-non-reasoning",
            ledger_path=self.ledger, provider="xai",
            envelope="frontier", required_terms=("lane live",),
            auto_approve=True, loop_class="lower-order",
            routing_class="qr-live-wire",
            transport=lambda m, p: xai_raw(),
        )
        self.assertEqual(row["status"], "approved")
        rec = self._final_dispatch_record()
        self.assertEqual(rec["routing"]["nature"], "probabilistic")

    def test_unrouted_test0_blocked_before_dispatch(self):
        row = cli.run(
            "anything", "claude-haiku-5-5",
            ledger_path=self.ledger, provider="anthropic",
            envelope="frontier", auto_approve=True,
            input_manifest={"life_domain": "research",
                            "query_nature": "analysis",
                            "data": {"source_class": "owner",
                                     "provenance": "test",
                                     "sensitivity": "compartmented"}},
            transport=boom_transport,
        )
        self.assertEqual(row["status"], "blocked-router:test-0")


if __name__ == "__main__":
    unittest.main()
