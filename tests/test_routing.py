"""Routing Table v0 tests: chokepoint admission, TEST-0, B7, stamps.

Run: python -m unittest tests.test_routing -v
"""

import json
import os
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from gated_dispatch import cli, prompts, routing, throttle  # noqa: E402


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
        self.assertEqual(d.stamp["table_version"], "v0.4")
        self.assertEqual(d.stamp["table_hash"], routing.TABLE_HASH)

    def test_spread_seats_admitted_v01(self):
        # Table v0.1 (2026-11-17, routing-spread directive): the
        # non-Claude seats seated by the rebalance resolve at their
        # chain positions; ruling containment is unchanged.
        d = routing.resolve("qr-coding-burst", "openrouter",
                            "north-mini-code")
        self.assertTrue(d.allowed)
        self.assertEqual(d.stamp["position"], "chain-0")
        self.assertEqual(routing.select("qr-coding-burst"),
                         ("openrouter", "north-mini-code"))
        d = routing.resolve("qr-panel-verdict", "openrouter",
                            "nemotron-3-ultra")
        self.assertTrue(d.allowed)
        self.assertEqual(d.stamp["position"], "chain-1")
        d = routing.resolve("qr-research", "openrouter",
                            "nemotron-3-ultra")
        self.assertTrue(d.allowed)
        self.assertEqual(d.stamp["position"], "chain-1")
        d = routing.resolve("qr-canon-drafting", "google",
                            "gemini-3.6-flash")
        self.assertTrue(d.allowed)
        self.assertEqual(d.stamp["position"], "chain-0")
        d = routing.resolve("qr-content-voice", "xai",
                            "grok-4.20-0309-non-reasoning")
        self.assertTrue(d.allowed)
        self.assertEqual(d.stamp["position"], "chain-1")
        d = routing.resolve("qr-commission-ruling", "openrouter",
                            "nemotron-3-ultra")
        self.assertFalse(d.allowed)

    def test_draft_check_designated_seat_v02(self):
        # Table v0.2 (2026-11-17, AR-20261117-06): the compliance
        # checker is a designated seat — opus admitted at chain-0,
        # every other frontier seat is a class mismatch, and the
        # class is NOT in JUDGMENT_CLASSES (no manifest gate taken).
        d = routing.resolve("qr-draft-check", "anthropic",
                            "claude-opus-5-5")
        self.assertTrue(d.allowed)
        self.assertEqual(d.stamp["position"], "chain-0")
        self.assertEqual(routing.select("qr-draft-check"),
                         ("anthropic", "claude-opus-5-5"))
        d = routing.resolve("qr-draft-check", "google",
                            "gemini-3.6-flash")
        self.assertFalse(d.allowed)
        self.assertEqual(d.cause, "class-mismatch")
        self.assertNotIn("qr-draft-check", routing.JUDGMENT_CLASSES)
        self.assertEqual(routing.resolve_nature("qr-draft-check"),
                         "probabilistic")

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
        self.assertEqual(s["table_version"], "v0.4")

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
        # The xAI lane hold is operational state (2026-11-17); the
        # live-wire fixture exercises grok service dispatch, so it
        # lifts the hold (test_lane_hold covers the hold itself).
        self._holds = throttle.LANE_HOLDS
        throttle.LANE_HOLDS = {}
        # v0.3 priming wrap: approved routed runs carry a verified
        # fixture stamp against a tmp catalogue.
        reg = os.path.join(self.dir, "registry.jsonl")
        rec = prompts.register(reg, "fx-priming", "task",
                               "fixture priming text", "test",
                               "v0.3 priming fixture")
        self.stamp = prompts.build_stamp([rec])
        env = mock.patch.dict(os.environ, {"GD_PROMPT_REGISTRY": reg})
        env.start()
        self.addCleanup(env.stop)

    def tearDown(self):
        throttle.LANE_HOLDS = self._holds

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
            prompt_stamp=self.stamp,
            transport=lambda m, p: xai_raw(),
        )
        self.assertEqual(row["status"], "approved")
        rec = self._final_dispatch_record()
        self.assertEqual(rec["routing"]["class"], "qr-live-wire")
        self.assertEqual(rec["routing"]["position"], "chain-0")
        self.assertEqual(rec["routing"]["table_version"], "v0.4")

    def test_draft_check_containment_refuses_commodity_walk(self):
        # v0.4.35 containment: a junior-loop draft check's throttle
        # walk lands on a commodity seat outside the class's
        # admitted set — the run refuses before the transport fires.
        row = cli.run(
            "anything", "claude-opus-5-5",
            ledger_path=self.ledger, provider="anthropic",
            auto_approve=True, loop_class="junior",
            routing_class="qr-draft-check",
            transport=boom_transport,
        )
        self.assertEqual(row["status"], "blocked-router:class-mismatch")
        rec = self._final_dispatch_record()
        self.assertEqual(rec["routing"]["class"], "qr-draft-check")
        self.assertEqual(rec["routing"]["table_version"], "v0.4")

    def test_draft_check_loop_serves_designated_seat(self):
        # The fail-closed draft-check loop class fires the checker
        # seat as itself; the verdict-shaped return approves.
        def anthropic_raw(text="PASS"):
            return {"model": "claude-opus-5-5",
                    "content": [{"type": "text", "text": text}],
                    "usage": {"input_tokens": 100,
                              "output_tokens": 10}}
        row = cli.run(
            "check this draft", "claude-opus-5-5",
            ledger_path=self.ledger, provider="anthropic",
            envelope="frontier", required_terms=("PASS",),
            auto_approve=True, loop_class="draft-check",
            routing_class="qr-draft-check",
            prompt_stamp=self.stamp,
            transport=lambda m, p: anthropic_raw(),
        )
        self.assertEqual(row["status"], "approved")
        self.assertEqual(row["model_served"], "claude-opus-5-5")
        rec = self._final_dispatch_record()
        self.assertEqual(rec["routing"]["class"], "qr-draft-check")

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
            prompt_stamp=self.stamp,
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


class FiveLaneTest(unittest.TestCase):
    """Table v0.3 (his commission 2026-11-17 23:22 CT): five natures,
    the model binding table, and the priming wrap."""

    def test_five_natures(self):
        self.assertEqual(
            routing.NATURES,
            ("deterministic", "algorithmic", "statistical",
             "reasoning", "probabilistic"))
        self.assertEqual(
            routing.resolve_nature("qr-research", "statistical"),
            "statistical")
        self.assertEqual(
            routing.resolve_nature("qr-research", "reasoning"),
            "reasoning")
        self.assertEqual(routing.TABLE_VERSION, "v0.4")

    def test_bindings_shape(self):
        self.assertEqual(routing.bindings_for("deterministic"), ())
        algo = {b.model for b in routing.bindings_for("algorithmic")}
        self.assertEqual(algo, {"qwen3:14b", "deepseek-r1:14b",
                                "llama3.1:8b"})
        stat = {b.model for b in routing.bindings_for("statistical")}
        self.assertEqual(stat, {"mistralai/voxtral-small-24b-2507",
                                "gemini-3.5-transcribe",
                                "tencent/hy4-flash",
                                "gemini-3.8-flash-lite-tts",
                                "gemini-3.5-flash"})
        reas = {b.model for b in routing.bindings_for("reasoning")}
        self.assertEqual(reas, {"deepseek/deepseek-v4.1-flash-1017",
                                "tencent/hy4-flash",
                                "grok-4.20-0309-non-reasoning",
                                "gemini-3.5-flash"})
        prob = {b.model for b in routing.bindings_for("probabilistic")}
        self.assertEqual(prob, {"claude-opus-5-5", "grok-imagine-image",
                                "gemini-3.1-flash-lite-image"})
        with self.assertRaises(ValueError):
            routing.bindings_for("holographic")

    def test_dispatchable_bindings_registered_and_priced(self):
        from gated_dispatch import pricing
        for key in ("statistical", "reasoning", "probabilistic"):
            for b in routing.bindings_for(key):
                if b.tier != "dispatchable":
                    continue
                self.assertIn(b.model, throttle.MODELS, b.model)
                pricing.price_info(b.provider, b.model)

    def test_scenery_stays_unbound(self):
        # The annex classes both scenery: flash-lite text (cataloged
        # only) and the Grok reasoning variant (only non-reasoning
        # was smoked). Neither binds under any key.
        bound = {b.model for key in
                 ("deterministic", "algorithmic", "statistical",
                  "reasoning", "probabilistic")
                 for b in routing.bindings_for(key)}
        self.assertNotIn("gemini-3.1-flash-lite", bound)
        self.assertNotIn("grok-4.20-0309-reasoning", bound)
        self.assertNotIn("grok-imagine-video", bound)


class PrimingWrapTest(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp()
        self.ledger = os.path.join(self.dir, "l.jsonl")
        self._holds = throttle.LANE_HOLDS
        throttle.LANE_HOLDS = {}
        reg = os.path.join(self.dir, "registry.jsonl")
        rec = prompts.register(reg, "fx-priming", "task",
                               "fixture priming text", "test",
                               "v0.3 priming fixture")
        self.stamp = prompts.build_stamp([rec])
        self._rec = rec
        env = mock.patch.dict(os.environ, {"GD_PROMPT_REGISTRY": reg})
        env.start()
        self.addCleanup(env.stop)
        self.addCleanup(
            lambda: setattr(throttle, "LANE_HOLDS", self._holds))

    def _run(self, **kw):
        kw.setdefault("ledger_path", self.ledger)
        kw.setdefault("provider", "xai")
        kw.setdefault("envelope", "frontier")
        kw.setdefault("auto_approve", True)
        kw.setdefault("loop_class", "lower-order")
        kw.setdefault("routing_class", "qr-live-wire")
        kw.setdefault("required_terms", ("lane live",))
        return cli.run("Reply with exactly: lane live",
                       "grok-4.20-0309-non-reasoning", **kw)

    def test_no_stamp_refuses(self):
        row = self._run(transport=boom_transport)
        self.assertEqual(row["status"], "blocked-priming:no-stamp")
        self.assertEqual(row["cost_usd"], 0.0)

    def test_unregistered_stamp_refuses(self):
        bad = prompts.build_stamp(
            [{"prompt_id": "ghost", "species": "task", "version": 1,
              "sha256": "0" * 64}])
        row = self._run(prompt_stamp=bad, transport=boom_transport)
        self.assertEqual(row["status"], "blocked-priming:unregistered")

    def test_hash_mismatch_refuses(self):
        bad = prompts.build_stamp(
            [dict(self._rec, sha256="0" * 64)])
        row = self._run(prompt_stamp=bad, transport=boom_transport)
        self.assertEqual(row["status"], "blocked-priming:hash-mismatch")

    def test_verified_stamp_proceeds(self):
        row = self._run(prompt_stamp=self.stamp,
                        transport=lambda m, p: xai_raw())
        self.assertEqual(row["status"], "approved")

    def test_named_mode_exempt(self):
        row = self._run(seat_mode="named",
                        transport=lambda m, p: xai_raw())
        self.assertEqual(row["status"], "approved")
