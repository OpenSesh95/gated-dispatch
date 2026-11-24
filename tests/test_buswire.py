"""The bus wire: lane mapping, the inert posture, and the
two-phase flow against a stubbed bus package.

Converted to the repo's unittest shape by the gate desk at
landing (2026-11-24): the handed-over file was pytest-style
(bare functions + the monkeypatch fixture) and collected ZERO
tests under this repo's unittest-discover CI — the conversion
preserves all four tests and every assertion, replacing
monkeypatch with unittest.mock.patch.object.
"""
import unittest
from unittest import mock

from gated_dispatch import buswire


class TestLaneMapping(unittest.TestCase):
    def test_lane_mapping(self):
        self.assertEqual(buswire.lane_for("anthropic"),
                         "realtime_api:anthropic")
        self.assertEqual(buswire.lane_for("openrouter", "google/gemini-x"),
                         "realtime_api:google")
        self.assertEqual(buswire.lane_for("openrouter", "openai/gpt-x"),
                         "realtime_api:openai")
        self.assertEqual(buswire.lane_for("local"), "local")
        self.assertEqual(buswire.lane_for("unknown-prov"), "seat_job")


class TestInertWithoutBus(unittest.TestCase):
    def test_wire_inert_without_bus(self):
        with mock.patch.object(buswire, "_bus", lambda: None):
            self.assertIsNone(
                buswire.decide("t-1", "qr-x", "anthropic", "m"))
            buswire.emit_outcome({"_task_id": "t-1"}, "anthropic", "m",
                                 1, 2)  # must not raise


class TestTwoPhaseWithStubBus(unittest.TestCase):
    def test_two_phase_with_stub_bus(self):
        seen = {}

        class Stub:
            @staticmethod
            def decide_route(task_id, task, seat_lane):
                seen["task"] = task
                seen["seat_lane"] = seat_lane
                return {"arm": "B", "seat_lane": seat_lane}

            @staticmethod
            def emit_route(desk, task_id, decision, **kw):
                seen["emit"] = (desk, task_id, kw)
                return 0

        with mock.patch.object(buswire, "_bus", lambda: Stub):
            ctx = buswire.decide("run-1", "qr-panel", "anthropic",
                                 "claude-x", test0=True)
            self.assertIsNotNone(ctx)
            self.assertIs(seen["task"]["custody_sensitive"], True)
            buswire.emit_outcome(ctx, "anthropic", "claude-x", 10, 5)
            desk, task_id, kw = seen["emit"]
            self.assertEqual(desk, "gated-dispatch")
            self.assertEqual(task_id, "run-1")
            self.assertEqual(kw["executed_lane"], "realtime_api:anthropic")
            self.assertEqual(kw["tokens"], (10, 5))


class TestGatedDecisionYieldsNoContext(unittest.TestCase):
    def test_gated_decision_yields_no_context(self):
        class Stub:
            @staticmethod
            def decide_route(task_id, task, seat_lane):
                return {"gated": "custody-sensitive (flagged)"}

        with mock.patch.object(buswire, "_bus", lambda: Stub):
            self.assertIsNone(
                buswire.decide("t-2", "qr-x", "anthropic", "m",
                               test0=True))


if __name__ == "__main__":
    unittest.main()
