"""Lane hold mechanism (gate v0.4.31) + lifted state (v0.4.32).

The mechanism: while a provider sits in throttle.LANE_HOLDS,
service dispatch to its seats stops as banned, chain walks skip
its candidates, and measurement (named mode) stays exempt so the
canary and credential proofs can still probe. The xAI hold stood
2026-11-17 ~11:5x-12:54 CT and was LIFTED when the /v1/models
proof passed on custom.grok — the registry is empty at rest, and
the behavior tests below inject a fixture hold to exercise the
mechanism.
"""

import contextlib
import os
import tempfile
import unittest

from gated_dispatch import cli, throttle


@contextlib.contextmanager
def fixture_hold():
    saved = throttle.LANE_HOLDS
    throttle.LANE_HOLDS = {"xai": "fixture hold for mechanism tests"}
    try:
        yield
    finally:
        throttle.LANE_HOLDS = saved


class LaneHoldTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.ledger = os.path.join(self.tmp.name, "ledger.jsonl")
        self.state = throttle.ThrottleState(
            os.path.join(self.tmp.name, "state.throttle.json"))

    def tearDown(self):
        self.tmp.cleanup()

    def test_registry_empty_at_rest(self):
        # The lifted state (2026-11-17 12:54 CT): no lane held, and
        # the grok seats resolve their hold check to None.
        self.assertEqual(throttle.LANE_HOLDS, {})
        self.assertIsNone(
            throttle.lane_hold("grok-4.20-0309-non-reasoning"))
        self.assertIsNone(
            throttle.lane_hold("grok-4.20-multi-agent-0309"))
        self.assertIsNone(throttle.lane_hold("claude-haiku-5-5"))

    def test_service_dispatch_to_held_seat_stops_banned(self):
        def boom(m, p):
            raise AssertionError("transport must not fire on a hold")

        with fixture_hold():
            row = cli.run(
                "Reply with exactly: lane live",
                "grok-4.20-0309-non-reasoning",
                ledger_path=self.ledger, provider="xai",
                envelope="frontier", auto_approve=True,
                loop_class="lower-order", transport=boom)
        self.assertEqual(row["status"], "blocked-throttle:banned-model")
        self.assertIn("lane held", str(row["checks"]))

    def test_named_mode_stays_exempt_for_proofs(self):
        with fixture_hold():
            res = throttle.resolve(
                "lower-order", "grok-4.20-0309-non-reasoning",
                self.state, now=1000.0, seat_mode="named")
        self.assertEqual(res.model, "grok-4.20-0309-non-reasoning")

    def test_chain_walk_skips_held_candidates(self):
        # Breach the head candidate's budget; the walk must pass
        # over the held xAI seat and land on the next live one.
        # (Requesting the held seat itself stops banned — see the
        # service-dispatch test — the skip binds mid-chain seats.)
        for _ in range(5):
            self.state.record_error("gemini-3.6-flash", 1000.0)
        with fixture_hold():
            res = throttle.resolve(
                "lower-order", "gemini-3.6-flash", self.state,
                now=1000.0,
                chain_order=["gemini-3.6-flash",
                             "grok-4.20-0309-non-reasoning",
                             "claude-haiku-5-5"])
        self.assertEqual(res.model, "claude-haiku-5-5")


if __name__ == "__main__":
    unittest.main()
