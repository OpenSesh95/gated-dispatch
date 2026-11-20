"""STD-0 tests: lane parsers, ticket completeness, envelope stops.

Run: python -m unittest discover -s tests -v
"""

import json
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import time  # noqa: E402

from gated_dispatch import bench, calibration, canary, extcal, inputs, livecost, certs, cli, contracts, dispatch_log, envelopes, lanes, mutants, preflight, pricing, prompts, ruling_lint, throttle, tssec, verify  # noqa: E402


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


def ollama_raw(text="lane live", model="qwen3:14b", tin=19, tout=5):
    return {
        "model": model,
        "choices": [{"message": {"content": text}}],
        "usage": {"prompt_tokens": tin, "completion_tokens": tout},
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

    def test_xai_reasoning_tokens_bill_as_output(self):
        # P-017 evidence (Treasury TR-20261112-09): xAI bills reasoning
        # at the output rate on top of completion; the list method that
        # omitted it understated the line x1.89.
        raw = xai_raw(model="grok-4.20-0309-reasoning", tin=6389, tout=1277)
        raw["usage"]["completion_tokens_details"] = {"reasoning_tokens": 4047}
        c = lanes.parse_xai(raw)
        self.assertEqual((c.tokens_in, c.tokens_out), (6389, 1277 + 4047))
        cost = pricing.estimate_cost_usd("xai", "grok-4.20-0309-reasoning", c.tokens_in, c.tokens_out)
        self.assertAlmostEqual(cost, 0.0213, places=4)

    def test_xai_base_model_id_is_priced(self):
        self.assertEqual(
            pricing.price_info("xai", "grok-4.20")[:2], (1.25, 2.50)
        )


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
        # Throttle v1: a model that is neither allowlisted nor priced
        # stops at the FIRST gate that refuses it — the allowlist.
        # The STD-0 claim this test pins is unchanged: no dispatch fires.
        self.assertEqual(row["status"], "blocked-throttle:banned-model")
        self.assertEqual(called, [])

    def test_allowlist_never_outruns_price_table(self):
        # Invariant: every throttle-allowlisted model is priced, so an
        # allowlisted dispatch can never die at the unmetered stop.
        for model, rule in throttle.MODELS.items():
            pricing.price_info(rule.provider, model)

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


def xai_stub(text="lane live", tin=10, tout=5):
    def _transport(model, prompt):
        return {
            "model": model,
            "choices": [{"message": {"content": text}}],
            "usage": {"prompt_tokens": tin, "completion_tokens": tout},
        }
    return _transport


class ThrottleTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.ledger = os.path.join(self.tmp.name, "ledger.jsonl")
        self.dlog = os.path.join(self.tmp.name, "ledger.dispatch.jsonl")
        self.tstate = os.path.join(self.tmp.name, "ledger.throttle.json")
        # The xAI lane hold is operational state (2026-11-17); these
        # fixtures exercise grok service dispatch, so they lift it.
        self._holds = throttle.LANE_HOLDS
        throttle.LANE_HOLDS = {}

    def tearDown(self):
        throttle.LANE_HOLDS = self._holds
        self.tmp.cleanup()

    def _records(self):
        with open(self.dlog, encoding="utf-8") as fh:
            return [json.loads(line) for line in fh if line.strip()]

    def _run(self, prompt, model, **kw):
        kw.setdefault("ledger_path", self.ledger)
        kw.setdefault("auto_approve", True)
        return cli.run(prompt, model, **kw)

    def test_latest_alias_is_banned(self):
        row = self._run("hi", "gemini-3.8-flash-latest", provider="google",
                        transport=xai_stub())
        self.assertEqual(row["status"], "blocked-throttle:banned-model")
        rec = self._records()[-1]
        self.assertEqual(rec["run_outcome"], "blocked-throttle:banned-model")
        self.assertEqual(rec["attempt_no"], 0)
        self.assertEqual(rec["loop_id"], row["ticket"])

    def test_retired_model_is_banned(self):
        with self.assertRaises(throttle.BannedModel):
            throttle.check_model("gemini-2.5-flash")

    def test_commodity_degrades_on_budget_breach(self):
        state = throttle.ThrottleState(self.tstate)
        now = time.time()
        for _ in range(3):
            state.record_error("gemini-3.6-flash", now)
        row = self._run("hi", "gemini-3.6-flash", provider="google",
                        loop_class="sweep", transport=xai_stub())
        self.assertEqual(row["status"], "approved")
        # Post-spread (gate v0.4.29, routing table v0.1): the
        # commodity walk ranks the free OpenRouter head first, so
        # the degrade lands on nemotron-3-ultra, not the pre-spread
        # grok pick; the :free serve books free-tier, not list.
        self.assertEqual(row["model"], "nemotron-3-ultra")
        self.assertEqual(row["checks"]["throttle_degraded_from"], "gemini-3.6-flash")
        recs = self._records()
        self.assertEqual(recs[0]["degraded_from"], "gemini-3.6-flash")
        self.assertEqual(recs[-1]["loop_class"], "lower-order")
        self.assertEqual(recs[-1]["run_outcome"], "approved")
        self.assertEqual(recs[-1]["cost_source"], "free-tier")

    def test_deliberative_fails_closed_on_budget_breach(self):
        state = throttle.ThrottleState(self.tstate)
        now = time.time()
        for _ in range(3):
            state.record_error("gemini-3.5-flash", now)

        def forbidden(model, prompt):
            raise AssertionError("deliberative stop must not fire the lane")

        row = self._run("hi", "gemini-3.5-flash", provider="google",
                        loop_class="panel", transport=forbidden)
        self.assertEqual(row["status"], "blocked-throttle:error-budget")

    def test_retries_counted_and_recorded(self):
        calls = {"n": 0}

        def flaky(model, prompt):
            calls["n"] += 1
            if calls["n"] < 3:
                raise ConnectionError("503 from lane")
            return {
                "model": model,
                "choices": [{"message": {"content": "lane live"}}],
                "usage": {"prompt_tokens": 10, "completion_tokens": 5},
            }

        row = self._run("hi", "grok-4.20-0309-non-reasoning", provider="xai",
                        loop_class="panel", transport=flaky,
                        _sleep_fn=lambda s: None)
        self.assertEqual(row["status"], "approved")
        recs = self._records()
        self.assertEqual([r["attempt_no"] for r in recs], [1, 2, 3])
        self.assertEqual([r["outcome"] for r in recs], ["fail", "fail", "success"])
        self.assertTrue(all(r["loop_id"] == row["ticket"] for r in recs))
        self.assertEqual(recs[-1]["form_gate_pass"], True)
        self.assertIsNone(recs[-1]["trace_fidelity"])

    def test_concurrency_slots(self):
        state = throttle.ThrottleState(self.tstate)
        now = time.time()
        self.assertTrue(state.try_acquire("claude-haiku-5-5", now))
        self.assertTrue(state.try_acquire("claude-haiku-5-5", now))
        self.assertTrue(state.try_acquire("claude-haiku-5-5", now))
        self.assertFalse(state.try_acquire("claude-haiku-5-5", now))
        state.release("claude-haiku-5-5")
        self.assertTrue(state.try_acquire("claude-haiku-5-5", now))


class DispatchLogTest(unittest.TestCase):
    def _rec(self, path, loop_id, lat, outcome="success", run_outcome=None,
             q="what is the airspeed of a swallow"):
        return dispatch_log.append_record(
            path, loop_id=loop_id, loop_class="lower-order", seat="google",
            model="gemini-3.8-flash", attempt_no=1,
            ts_dispatch="2026-11-12T00:00:00+00:00",
            ts_outcome="2026-11-12T00:00:01+00:00",
            latency=lat, total_tokens=100, outcome=outcome,
            run_outcome=run_outcome,
            question_key=dispatch_log.question_key(q),
            question_shingles=dispatch_log.question_shingles(q),
        )

    def test_size_bands(self):
        self.assertEqual(dispatch_log.size_band(25_000), "mechanical")
        self.assertEqual(dispatch_log.size_band(25_001), "execution")
        self.assertEqual(dispatch_log.size_band(120_000), "reasoning")
        self.assertEqual(dispatch_log.size_band(120_001), "L4")

    def test_summarize_p50_p95(self):
        tmp = tempfile.TemporaryDirectory()
        path = os.path.join(tmp.name, "d.jsonl")
        for i, lat in enumerate([1.0, 2.0, 3.0, 4.0, 10.0]):
            self._rec(path, f"GD-T-{i}", lat, run_outcome="approved",
                      q=f"unique question number {i} about topic {i}")
        # The fixtures are stamped 2026-11-12; anchor `now` to their
        # day so the rolling 7-day window holds them deterministically
        # (the wall-clock window aged them out on 2026-11-19).
        from datetime import datetime, timezone
        out = dispatch_log.summarize(
            path, now=datetime(2026, 11, 12, 2, 0, tzinfo=timezone.utc))
        self.assertEqual(out["lower-order"]["attempts"], 5)
        self.assertEqual(out["lower-order"]["p50"], 3.0)
        self.assertEqual(out["lower-order"]["p95"], 10.0)
        self.assertEqual(out["lower-order"]["repeat_question_rate"], 0.0)
        tmp.cleanup()

    def test_repeat_question_rate(self):
        tmp = tempfile.TemporaryDirectory()
        path = os.path.join(tmp.name, "d.jsonl")
        now = None
        from datetime import datetime, timezone
        now = datetime.now(timezone.utc)
        for i in range(2):  # same question twice, both approved
            rec = self._rec(path, f"GD-R-{i}", 1.0, run_outcome="approved")
            # restamp into the live window
            import json as _json
            lines = open(path).read().splitlines()
            d = _json.loads(lines[-1]); d["ts_outcome"] = now.isoformat(timespec="seconds")
            lines[-1] = _json.dumps(d)
            open(path, "w").write("\n".join(lines) + "\n")
        out = dispatch_log.summarize(path, now=now)
        self.assertEqual(out["lower-order"]["loops"], 2)
        self.assertEqual(out["lower-order"]["repeat_loops"], 1)
        self.assertEqual(out["lower-order"]["repeat_question_rate"], 0.5)
        # v1.2 strata: exact and fuzzy publish side by side.
        self.assertEqual(out["lower-order"]["repeat_exact_rate"], 0.5)
        self.assertEqual(out["lower-order"]["repeat_fuzzy_rate"], 0.0)
        tmp.cleanup()

    def test_repeat_fuzzy_and_small_set_floor(self):
        from datetime import datetime, timezone
        now = datetime.now(timezone.utc)
        tmp = tempfile.TemporaryDirectory()
        path = os.path.join(tmp.name, "d.jsonl")
        long_q = " ".join(f"word{i}" for i in range(12))
        long_q2 = " ".join(f"word{i}" for i in range(11)) + " other"
        import json as _json

        def rec(loop_id, q, run_outcome="approved"):
            self._rec(path, loop_id, 1.0, run_outcome=run_outcome, q=q)
            lines = open(path).read().splitlines()
            d = _json.loads(lines[-1]); d["ts_outcome"] = now.isoformat(timespec="seconds")
            lines[-1] = _json.dumps(d)
            open(path, "w").write("\n".join(lines) + "\n")

        rec("GD-F-1", long_q)
        rec("GD-F-2", long_q2)            # near-dup, >=8 shingles -> fuzzy
        rec("GD-F-3", "short question here now")
        rec("GD-F-4", "short question here today")  # <8 shingles -> no fuzzy
        out = dispatch_log.summarize(path, now=now)
        self.assertEqual(out["lower-order"]["repeat_fuzzy_loops"], 1)
        self.assertEqual(out["lower-order"]["repeat_exact_loops"], 0)
        tmp.cleanup()


class ProviderErrorBodyTest(unittest.TestCase):
    def test_error_body_normalizes_to_connection_error(self):
        def transport(model, prompt):
            return {"error": {"code": 503, "message": "model overloaded", "status": "UNAVAILABLE"}}
        with self.assertRaises(ConnectionError):
            lanes.dispatch("hi", "google", "gemini-3.8-flash", transport=transport)

    def test_helper_http_wrapper_normalizes(self):
        def transport(model, prompt):
            return {"http_status": 503,
                    "error_body": '{"error": {"code": 503, "message": "high demand", "status": "UNAVAILABLE"}}'}
        with self.assertRaises(ConnectionError):
            lanes.dispatch("hi", "google", "gemini-3.8-flash", transport=transport)


class HedgeAndStallTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.ledger = os.path.join(self.tmp.name, "ledger.jsonl")
        self.dlog = os.path.join(self.tmp.name, "ledger.dispatch.jsonl")
        # The xAI lane hold is operational state (2026-11-17); these
        # fixtures exercise grok service dispatch, so they lift it.
        self._holds = throttle.LANE_HOLDS
        throttle.LANE_HOLDS = {}

    def tearDown(self):
        throttle.LANE_HOLDS = self._holds
        self.tmp.cleanup()

    def _records(self):
        with open(self.dlog, encoding="utf-8") as fh:
            return [json.loads(line) for line in fh if line.strip()]

    def test_hedge_first_return_wins_loser_superseded(self):
        def transport(model, prompt):
            if model == "gemini-3.6-flash":
                time.sleep(0.5)
                return gemini_raw(text="lane live", model="gemini-3.6-flash")
            return {
                "model": model,
                "choices": [{"message": {"content": "lane live"}}],
                "usage": {"prompt_tokens": 10, "completion_tokens": 5},
            }

        row = cli.run("Reply with exactly: lane live", "gemini-3.6-flash",
                      ledger_path=self.ledger, provider="google",
                      loop_class="lower-order", auto_approve=True,
                      hedge=True, transport=transport)
        self.assertEqual(row["status"], "approved")
        # v0.1 spread (2026-11-17): the hedge partner is now the
        # chain's first ranked seat — nemotron-3-ultra, not grok.
        self.assertEqual(row["model"], "nemotron-3-ultra")
        self.assertIn("throttle_hedged", row["checks"])
        recs = self._records()
        self.assertEqual(len(recs), 2)
        self.assertEqual(recs[0]["outcome"], "success")
        self.assertEqual(recs[1]["outcome"], "superseded")
        self.assertEqual(recs[1]["model"], "gemini-3.6-flash")

    def test_hedge_never_fires_for_deliberative(self):
        row = cli.run("hi", "grok-4.20-0309-non-reasoning",
                      ledger_path=self.ledger, provider="xai",
                      loop_class="panel", auto_approve=True,
                      hedge=True, transport=xai_stub())
        self.assertEqual(row["status"], "approved")
        self.assertEqual(len(self._records()), 1)

    def test_stall_cause_and_hop_count(self):
        row = cli.run("hi", "gemini-9.9-flash-latest", ledger_path=self.ledger,
                      provider="google", auto_approve=True, hop_count=2,
                      transport=xai_stub())
        self.assertEqual(row["status"], "blocked-throttle:banned-model")
        rec = self._records()[-1]
        self.assertEqual(rec["stall_cause"], "banned-model")
        self.assertEqual(rec["hop_count"], 2)

        row2 = cli.run("hi", "grok-4.20-0309-non-reasoning",
                       ledger_path=self.ledger, provider="xai",
                       auto_approve=True, transport=xai_stub())
        self.assertEqual(row2["status"], "approved")
        rec2 = self._records()[-1]
        self.assertIsNone(rec2["stall_cause"])
        self.assertEqual(rec2["hop_count"], 0)

    def test_provider_error_stall_cause(self):
        def down(model, prompt):
            raise ConnectionError("lane down")

        row = cli.run("hi", "grok-4.20-0309-non-reasoning",
                      ledger_path=self.ledger, provider="xai",
                      loop_class="panel", auto_approve=True,
                      transport=down, _sleep_fn=lambda s: None)
        self.assertTrue(row["status"].startswith("error:"))
        rec = self._records()[-1]
        self.assertEqual(rec["stall_cause"], "provider-error")

    def test_unpriced_served_model_gets_proper_stop(self):
        # Served-model drift to an unpriced id must end as
        # error:unmetered-served-model, never as a bare KeyError.
        def transport(model, prompt):
            raw = gemini_raw(text="lane live")
            raw["modelVersion"] = "gemini-9.9-unpriced"
            return raw

        row = cli.run("hi", "gemini-3.8-flash", ledger_path=self.ledger,
                      provider="google", auto_approve=True, transport=transport)
        self.assertEqual(row["status"], "error:unmetered-served-model")

    def test_operator_study_fields_and_stability(self):
        row = cli.run("hi", "grok-4.20-0309-non-reasoning",
                      ledger_path=self.ledger, provider="xai",
                      auto_approve=True, transport=xai_stub(),
                      seat_confidence=0.8, seat_contribution=0.5)
        self.assertEqual(row["status"], "approved")
        rec = self._records()[-1]
        self.assertEqual(rec["seat_confidence"], 0.8)
        self.assertEqual(rec["seat_contribution"], 0.5)
        self.assertIsNotNone(rec["verify_ms"])
        self.assertEqual(rec["verify_cost_usd"], 0.0)
        summary = dispatch_log.summarize(self.dlog)
        stab = summary["_stability"]["grok-4.20-0309-non-reasoning"]
        self.assertEqual(stab["attempts"], 1)
        self.assertEqual(stab["success_share"], 1.0)

    def test_treasury_aggregate_rules(self):
        cli.run("hi", "grok-4.20-0309-non-reasoning",
                ledger_path=self.ledger, provider="xai",
                loop_class="junior", auto_approve=True, transport=xai_stub(),
                seat_confidence=0.8, seat_contribution=0.5)
        cli.run("hi", "grok-4.20-0309-non-reasoning",
                ledger_path=self.ledger, provider="xai",
                loop_class="junior", auto_approve=True, transport=xai_stub())
        summary = dispatch_log.summarize(self.dlog)
        view = summary["junior"]
        self.assertEqual(view["seat_confidence_mean"], 0.8)
        self.assertEqual(view["seat_confidence_coverage"], 0.5)
        self.assertIn("cost_per_successful_loop", view)
        self.assertEqual(view["all_in_cost_per_successful_loop"],
                         view["cost_per_successful_loop"])  # verify cost is $0
        stab = summary["_stability"]["grok-4.20-0309-non-reasoning"]
        self.assertEqual(stab["attempts"], 2)


class ResponsesTransportTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.ledger = os.path.join(self.tmp.name, "ledger.jsonl")
        self.dlog = os.path.join(self.tmp.name, "ledger.dispatch.jsonl")
        # The xAI lane hold is operational state (2026-11-17); these
        # fixtures exercise grok service dispatch, so they lift it.
        self._holds = throttle.LANE_HOLDS
        throttle.LANE_HOLDS = {}

    def tearDown(self):
        throttle.LANE_HOLDS = self._holds
        self.tmp.cleanup()

    @staticmethod
    def responses_raw():
        return {
            "model": "grok-4.20-multi-agent-0309",
            "object": "response",
            "output": [{
                "type": "message", "role": "assistant",
                "content": [{"type": "output_text", "text": "lane live"}],
            }],
            "usage": {
                "input_tokens": 6418, "output_tokens": 1505,
                "input_tokens_details": {"cached_tokens": 5248},
                "output_tokens_details": {"reasoning_tokens": 1387},
                "cost_in_usd_ticks": 62746000,
            },
        }

    def test_request_routes_to_responses_endpoint(self):
        path, body = lanes.request_for("xai", "grok-4.20-multi-agent-0309", "hi")
        self.assertEqual(path, "/v1/responses")
        self.assertEqual(body["input"], "hi")
        path2, _ = lanes.request_for("xai", "grok-4.20-0309-non-reasoning", "hi")
        self.assertEqual(path2, "/v1/chat/completions")

    def test_parse_responses_shape_no_double_reasoning(self):
        comp = lanes.dispatch("hi", "xai", "grok-4.20-multi-agent-0309",
                              transport=lambda m, p: self.responses_raw())
        self.assertEqual(comp.text, "lane live")
        self.assertEqual(comp.tokens_in, 6418)
        self.assertEqual(comp.tokens_out, 1505)  # reasoning already inside

    def test_gated_run_meters_ticks_exactly(self):
        row = cli.run("Reply with exactly: lane live", "grok-4.20-multi-agent-0309",
                      ledger_path=self.ledger, provider="xai",
                      loop_class="panel", auto_approve=True,
                      transport=lambda m, p: self.responses_raw())
        self.assertEqual(row["status"], "approved")
        with open(self.dlog, encoding="utf-8") as fh:
            rec = [json.loads(line) for line in fh if line.strip()][-1]
        self.assertEqual(rec["cost_source"], "ticks")
        self.assertEqual(rec["cost_usd"], 0.006275)  # 62,746,000 ticks

    def test_null_error_key_is_not_a_failure(self):
        raw = self.responses_raw()
        raw["error"] = None
        comp = lanes.dispatch("hi", "xai", "grok-4.20-multi-agent-0309",
                              transport=lambda m, p: raw)
        self.assertEqual(comp.text, "lane live")

    def test_google_cost_source_reads_list_on_paid_tier(self):
        # P-024 item 1: the free-tier label misstated the source.
        def transport(model, prompt):
            return gemini_raw(text="lane live")
        row = cli.run("hi", "gemini-3.8-flash", ledger_path=self.ledger,
                      provider="google", auto_approve=True, transport=transport)
        self.assertEqual(row["status"], "approved")
        with open(self.dlog, encoding="utf-8") as fh:
            rec = [json.loads(line) for line in fh if line.strip()][-1]
        self.assertEqual(rec["cost_source"], "list")


class C023BatchAndRulingsTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.ledger = os.path.join(self.tmp.name, "ledger.jsonl")
        self.dlog = os.path.join(self.tmp.name, "ledger.dispatch.jsonl")
        self.tstate = os.path.join(self.tmp.name, "ledger.throttle.json")

    def tearDown(self):
        self.tmp.cleanup()

    def _records(self):
        with open(self.dlog, encoding="utf-8") as fh:
            return [json.loads(line) for line in fh if line.strip()]

    def test_repin_commodity_35_fires_pin_labeled(self):
        row = cli.run("hi", "gemini-3.5-flash", ledger_path=self.ledger,
                      provider="google", loop_class="junior",
                      auto_approve=True, transport=lambda m, p: gemini_raw())
        self.assertEqual(row["status"], "approved")
        self.assertEqual(row["model"], "gemini-3.6-flash")
        self.assertIn("repinned", row["checks"].get("throttle_note", ""))
        self.assertEqual(self._records()[-1]["degraded_from"], "gemini-3.5-flash")

    def test_deliberative_35_fires_as_requested(self):
        row = cli.run("hi", "gemini-3.5-flash", ledger_path=self.ledger,
                      provider="google", loop_class="panel",
                      auto_approve=True, transport=lambda m, p: gemini_raw())
        self.assertEqual(row["status"], "approved")
        self.assertEqual(row["model"], "gemini-3.5-flash")

    def test_37_quarantined_at_gate(self):
        row = cli.run("hi", "gemini-3.7-flash", ledger_path=self.ledger,
                      provider="google", auto_approve=True,
                      transport=lambda m, p: gemini_raw())
        self.assertEqual(row["status"], "blocked-throttle:banned-model")

    def test_gemma_cost_source_free_tier(self):
        # The gemma seat serves via the OpenRouter wired lane
        # (OPENROUTER_SERVE_MAP, C-038 wiring): a google-provider
        # request re-pins to it, so the run rides the openrouter
        # transport shape. Booked $0 with cost_source free-tier —
        # the assertion this test was written for, on the lane
        # that actually serves the seat today.
        row = cli.run("hi", "gemma-4-31b-it", ledger_path=self.ledger,
                      provider="openrouter", loop_class="panel",
                      auto_approve=True, transport=xai_stub())
        self.assertEqual(row["status"], "approved")
        rec = self._records()[-1]
        self.assertEqual(rec["cost_source"], "free-tier")
        self.assertEqual(rec["cost_usd"], 0.0)

    def test_probation_trigger_quarantines_38(self):
        state = throttle.ThrottleState(self.tstate)
        now = 1_000_000.0
        for i in range(3):
            state.record_error("gemini-3.8-flash", now + i)
        self.assertTrue(state.is_quarantined("gemini-3.8-flash"))
        with self.assertRaises(throttle.BannedModel):
            throttle.resolve("panel", "gemini-3.8-flash", state, now + 10)
    def test_gl15_named_measurement_exempt_from_probation(self):
        state = throttle.ThrottleState(self.tstate)
        now = 2_000_000.0
        for i in range(3):
            state.record_error("gemini-3.8-flash", now + i,
                               probation_exempt=True)
        self.assertFalse(state.is_quarantined("gemini-3.8-flash"))
        for i in range(3):
            state.record_error("gemini-3.8-flash", now + i)
        self.assertTrue(state.is_quarantined("gemini-3.8-flash"))
        # service path stays blocked; measurement is exempt by rule
        with self.assertRaises(throttle.BannedModel):
            throttle.resolve("panel", "gemini-3.8-flash", state, now + 10)
        res = throttle.resolve("junior", "gemini-3.8-flash", state,
                               now + 3600, seat_mode="named")
        self.assertEqual(res.model, "gemini-3.8-flash")



class NamedSeatModeTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.ledger = os.path.join(self.tmp.name, "ledger.jsonl")
        self.dlog = os.path.join(self.tmp.name, "ledger.dispatch.jsonl")
        self.tstate = os.path.join(self.tmp.name, "ledger.throttle.json")

    def tearDown(self):
        self.tmp.cleanup()

    def _records(self):
        with open(self.dlog, encoding="utf-8") as fh:
            return [json.loads(line) for line in fh if line.strip()]

    def test_named_fires_non_chain_seat_as_itself(self):
        row = cli.run("hi", "gemini-3.5-flash-lite", ledger_path=self.ledger,
                      provider="google", loop_class="junior", seat_mode="named",
                      auto_approve=True,
                      transport=lambda m, p: gemini_raw(model="gemini-3.5-flash-lite"))
        self.assertEqual(row["status"], "approved")
        self.assertEqual(row["model"], "gemini-3.5-flash-lite")
        rec = self._records()[-1]
        self.assertIsNone(rec["degraded_from"])
        self.assertEqual(rec["seat_mode"], "named")
        self.assertEqual(rec["loop_class"], "junior")

    def test_chain_default_still_degrades(self):
        # Post-spread (gate v0.4.29): the chain walk's ranked pick
        # for an unregistered seat is the free OpenRouter head, so
        # the transport answers per served lane (gemini shape for
        # google seats, OpenAI shape for openrouter seats).
        def aware(m, p):
            if m.startswith(("gemini", "gemma")):
                return gemini_raw(model=m)
            return xai_stub()(m, p)
        row = cli.run("hi", "gemini-3.5-flash-lite", ledger_path=self.ledger,
                      provider="google", loop_class="junior",
                      auto_approve=True, transport=aware)
        self.assertEqual(row["model"], "nemotron-3-ultra")
        self.assertEqual(self._records()[-1]["seat_mode"], "chain")

    def test_named_breach_stops_without_degrade(self):
        state = throttle.ThrottleState(self.tstate)
        now = time.time()
        for _ in range(3):
            state.record_error("gemini-3.5-flash-lite", now)
        row = cli.run("hi", "gemini-3.5-flash-lite", ledger_path=self.ledger,
                      provider="google", loop_class="junior", seat_mode="named",
                      auto_approve=True,
                      transport=lambda m, p: gemini_raw())
        self.assertEqual(row["status"], "blocked-throttle:error-budget")

    def test_named_banned_model_still_stops(self):
        row = cli.run("hi", "gemini-3.7-flash", ledger_path=self.ledger,
                      provider="google", loop_class="junior", seat_mode="named",
                      auto_approve=True, transport=lambda m, p: gemini_raw())
        self.assertEqual(row["status"], "blocked-throttle:banned-model")
    def test_named_mode_invariants_for_the_meter(self):
        # Treasury §5.8 rule 2: a named record never carries
        # degraded_from, and no named attempt reads superseded.
        row = cli.run("hi", "gemini-3.5-flash-lite", ledger_path=self.ledger,
                      provider="google", loop_class="junior", seat_mode="named",
                      hedge=True, auto_approve=True,
                      transport=lambda m, p: gemini_raw(model="gemini-3.5-flash-lite"))
        self.assertEqual(row["status"], "approved")
        recs = self._records()
        self.assertTrue(all(r["degraded_from"] is None for r in recs))
        self.assertTrue(all(r["outcome"] != "superseded" for r in recs))
        self.assertTrue(all(r["seat_mode"] == "named" for r in recs
                            if r["run_outcome"] is not None))



class C026LinesTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.ledger = os.path.join(self.tmp.name, "ledger.jsonl")
        self.dlog = os.path.join(self.tmp.name, "ledger.dispatch.jsonl")
        self.tstate = os.path.join(self.tmp.name, "ledger.throttle.json")

    def tearDown(self):
        self.tmp.cleanup()

    def _records(self):
        with open(self.dlog, encoding="utf-8") as fh:
            return [json.loads(line) for line in fh if line.strip()]

    def test_queue_wait_on_final_record(self):
        row = cli.run("hi", "gemini-3.6-flash", ledger_path=self.ledger,
                      provider="google", loop_class="panel",
                      auto_approve=True,
                      transport=lambda m, p: gemini_raw(model="gemini-3.6-flash"))
        self.assertEqual(row["status"], "approved")
        qw = self._records()[-1]["queue_wait"]
        self.assertIsInstance(qw, float)
        self.assertGreaterEqual(qw, 0.0)

    def test_queue_wait_on_concurrency_stop(self):
        state = throttle.ThrottleState(self.tstate)
        for _ in range(throttle.MODELS["claude-haiku-5-5"].concurrency):
            self.assertTrue(state.try_acquire("claude-haiku-5-5", time.time()))
        old = cli.ACQUIRE_TIMEOUT_S
        cli.ACQUIRE_TIMEOUT_S = 0.3
        try:
            row = cli.run("hi", "claude-haiku-5-5", ledger_path=self.ledger,
                          provider="anthropic", auto_approve=True,
                          transport=lambda m, p: anthropic_raw())
        finally:
            cli.ACQUIRE_TIMEOUT_S = old
        self.assertEqual(row["status"], "blocked-throttle:concurrency")
        qw = self._records()[-1]["queue_wait"]
        self.assertGreaterEqual(qw, 0.3)
        self.assertLess(qw, 2.0)

    def test_warm_only_cold_lanes_and_never_raises(self):
        self.assertFalse(lanes.warm("google", "gemini-3.6-flash",
                                    transport=lambda m, p: {}))
        self.assertTrue(lanes.warm("local", "qwen3:14b",
                                   transport=lambda m, p: {}))

        def boom(m, p):
            raise ConnectionError("down")
        self.assertFalse(lanes.warm("local", "qwen3:14b", transport=boom))

    def test_lane_scoped_timeout_map(self):
        self.assertEqual(cli.ACQUIRE_TIMEOUT_BY_PROVIDER["local"], 240.0)
        self.assertEqual(cli.ACQUIRE_TIMEOUT_S, 120.0)


class PriorityQueueTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.tstate = os.path.join(self.tmp.name, "state.throttle.json")
        self.state = throttle.ThrottleState(self.tstate)

    def tearDown(self):
        self.tmp.cleanup()

    def test_class_rank_orders_the_queue(self):
        now = 5_000.0
        self.state.enqueue("gemini-3.6-flash", "w-low", "lower-order", now)
        self.state.enqueue("gemini-3.6-flash", "w-ruling", "ruling", now + 1)
        self.assertEqual(self.state.queue_head("gemini-3.6-flash", now + 2),
                         "w-ruling")

    def test_aging_lifts_a_starved_waiter(self):
        now = 5_000.0
        self.state.enqueue("gemini-3.6-flash", "w-low", "lower-order", now)
        self.state.enqueue("gemini-3.6-flash", "w-ruling", "ruling", now + 290)
        # 300 s waited: rank 5 - 6 steps -> 0; ties break by arrival.
        self.assertEqual(self.state.queue_head("gemini-3.6-flash", now + 300),
                         "w-low")
        self.assertEqual(throttle.effective_rank("lower-order", 300.0), 0)
        self.assertEqual(throttle.effective_rank("lower-order", 44.0), 5)

    def test_dequeue_and_stale_prune(self):
        now = 5_000.0
        self.state.enqueue("gemini-3.6-flash", "w-old", "panel", now)
        self.state.enqueue("gemini-3.6-flash", "w-new", "panel",
                           now + throttle.QUEUE_STALE_S + 10)
        snap = self.state.queue_snapshot("gemini-3.6-flash",
                                         now + throttle.QUEUE_STALE_S + 10)
        self.assertEqual([e["waiter"] for e in snap], ["w-new"])
        self.state.dequeue("gemini-3.6-flash", "w-new")
        self.assertEqual(self.state.queue_snapshot(
            "gemini-3.6-flash", now + throttle.QUEUE_STALE_S + 10), [])

    def test_grant_order_follows_class_not_arrival(self):
        import threading
        tmp = tempfile.TemporaryDirectory()
        shared_state = os.path.join(tmp.name, "shared.throttle.json")
        order = []

        def transport(model, prompt):
            time.sleep(1.2)
            return gemini_raw(model="gemini-3.6-flash")

        def worker(tag, loop_class, delay):
            time.sleep(delay)
            ledger = os.path.join(tmp.name, f"{tag}.jsonl")
            row = cli.run("hi", "gemini-3.6-flash", ledger_path=ledger,
                          provider="google", loop_class=loop_class,
                          throttle_state_path=shared_state,
                          auto_approve=True, transport=transport)
            order.append((tag, row["status"]))

        t1 = threading.Thread(target=worker, args=("first", "panel", 0.0))
        t2 = threading.Thread(target=worker, args=("low", "lower-order", 0.3))
        t3 = threading.Thread(target=worker, args=("high", "ruling", 0.6))
        t1.start(); t2.start(); t3.start()
        t1.join(); t2.join(); t3.join()
        tmp.cleanup()
        self.assertEqual([tag for tag, _ in order], ["first", "high", "low"])
        self.assertTrue(all(s == "approved" for _, s in order))



class PreflightTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.ledger = os.path.join(self.tmp.name, "pf.jsonl")

    def tearDown(self):
        self.tmp.cleanup()

    def test_named_leg_passes_all_checks(self):
        legs = [{"leg": "proposer", "model": "gemini-3.5-flash-lite",
                 "provider": "google", "loop_class": "junior",
                 "seat_mode": "named"}]
        rec = preflight.preflight(
            legs, ledger_path=self.ledger,
            transport=lambda m, p: gemini_raw(model="gemini-3.5-flash-lite"))
        self.assertEqual(rec["verdict"], "PASS")
        self.assertTrue(all(rec["legs"][0]["checks"].values()))
        self.assertIsNotNone(rec["legs"][0]["proof_ticket"])

    def test_resolve_mismatch_blocks_before_any_proof(self):
        legs = [{"leg": "proposer", "model": "gemini-3.5-flash-lite",
                 "provider": "google", "loop_class": "junior",
                 "seat_mode": "chain"}]  # chain resolves lite -> pin 3.6
        rec = preflight.preflight(
            legs, ledger_path=self.ledger,
            transport=lambda m, p: gemini_raw(model="gemini-3.6-flash"))
        self.assertEqual(rec["verdict"], "BLOCKED")
        leg = rec["legs"][0]
        self.assertFalse(leg["checks"]["resolves"])
        self.assertIsNone(leg["proof_ticket"])  # no proof fired

    def test_undeclared_seat_mode_blocks(self):
        legs = [{"leg": "proposer", "model": "gemini-3.6-flash",
                 "provider": "google", "loop_class": "panel"}]
        rec = preflight.preflight(legs, ledger_path=self.ledger,
                                  transport=lambda m, p: gemini_raw())
        self.assertEqual(rec["verdict"], "BLOCKED")
        self.assertFalse(rec["legs"][0]["checks"]["seat_mode_declared"])

    def test_served_mismatch_blocks(self):
        legs = [{"leg": "proposer", "model": "gemini-3.5-flash",
                 "provider": "google", "loop_class": "panel",
                 "seat_mode": "chain"}]
        rec = preflight.preflight(
            legs, ledger_path=self.ledger,
            transport=lambda m, p: gemini_raw(model="gemini-3.8-flash"))
        self.assertEqual(rec["verdict"], "BLOCKED")
        self.assertFalse(rec["legs"][0]["checks"]["serves"])



class GcpLaneTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.ledger = os.path.join(self.tmp.name, "ledger.jsonl")
        self.dlog = os.path.join(self.tmp.name, "ledger.dispatch.jsonl")

    def tearDown(self):
        self.tmp.cleanup()

    def test_gcp_dispatch_records_seat_and_grant_offset(self):
        row = cli.run("Reply with exactly: lane live", "qwen3:14b",
                      ledger_path=self.ledger, provider="gcp",
                      loop_class="panel", auto_approve=True,
                      transport=lambda m, p: ollama_raw())
        self.assertEqual(row["status"], "approved")
        self.assertEqual(row["provider"], "gcp")
        with open(self.dlog, encoding="utf-8") as fh:
            rec = [json.loads(l) for l in fh if l.strip()][-1]
        self.assertEqual(rec["cost_source"], "grant-offset")
        self.assertEqual(rec["cost_usd"], 0.0)

    def test_local_seat_still_records_local(self):
        row = cli.run("Reply with exactly: lane live", "qwen3:14b",
                      ledger_path=self.ledger, provider="local",
                      loop_class="panel", auto_approve=True,
                      transport=lambda m, p: ollama_raw())
        self.assertEqual(row["provider"], "local")


class DBench1Test(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.ledger = os.path.join(self.tmp.name, "ledger.jsonl")
        self.dlog = os.path.join(self.tmp.name, "ledger.dispatch.jsonl")

    def tearDown(self):
        self.tmp.cleanup()

    def _feed(self):
        with open(self.dlog, encoding="utf-8") as fh:
            return [json.loads(l) for l in fh if l.strip()]

    def test_env_and_profile_version_ride_the_records(self):
        cli.run("Reply with exactly: lane live", "gemini-3.6-flash",
                ledger_path=self.ledger, provider="google",
                loop_class="panel", auto_approve=True,
                env="cert", profile_version="profiles-v0.2.0",
                transport=lambda m, p: gemini_raw(model="gemini-3.6-flash"))
        feed = self._feed()
        self.assertTrue(all(r["env"] == "cert" for r in feed))
        self.assertEqual(feed[-1]["profile_version"], "profiles-v0.2.0")

    def test_invalid_env_stops_loudly(self):
        with self.assertRaises(ValueError):
            cli.run("x", "gemini-3.6-flash", ledger_path=self.ledger,
                    provider="google", env="staging",
                    transport=lambda m, p: gemini_raw())

    def test_summary_math_and_pending_default(self):
        cli.run("Reply with exactly: lane live", "gemini-3.6-flash",
                ledger_path=self.ledger, provider="google",
                loop_class="panel", auto_approve=True,
                transport=lambda m, p: gemini_raw(model="gemini-3.6-flash"))
        s = bench.summarize_loop(self._feed())
        self.assertEqual(s["decision_ready"], "PENDING")
        self.assertEqual(s["judged_by"], "follow-up-record")
        self.assertEqual(s["value_per_owner_minute"], "UNMEASURED")
        # the feed's timestamps carry second grain: a same-second
        # run reads wall 0.0; service carries the sub-second truth
        self.assertIsNotNone(s["wall_ms"])
        self.assertEqual(s["service_ms"],
                         round(self._feed()[-1]["latency"] * 1000, 1))

    def test_stopped_loop_reads_false_by_the_gate_record(self):
        cli.run("x", "gemini-2.5-flash", ledger_path=self.ledger,
                provider="google", loop_class="panel", auto_approve=True,
                transport=lambda m, p: gemini_raw())
        s = bench.summarize_loop(self._feed())
        self.assertEqual(s["decision_ready"], "FALSE")
        self.assertEqual(s["judged_by"], "gate-record")

    def test_value_rules_by_cost_source(self):
        base = dict(loop_id="L", loop_class="panel", seat="google",
                    model="m", attempt_no=1,
                    ts_dispatch="2026-11-12T00:00:00+00:00",
                    ts_outcome="2026-11-12T00:00:02+00:00",
                    latency=2.0, tokens_in=10, tokens_out=5,
                    outcome="success", run_outcome="approved")
        judged = {"decision_ready": "TRUE", "judged_by": "gate-scorer"}
        s = bench.summarize_loop([dict(base, cost_usd=0.5,
                                       cost_source="list")], judged=judged)
        self.assertEqual(s["value_per_usd"], 2.0)
        s = bench.summarize_loop([dict(base, cost_usd=0.0,
                                       cost_source="local-zero")],
                                 judged=judged)
        self.assertEqual(s["value_per_usd"], "LOCAL-ZERO")
        s = bench.summarize_loop([dict(base, cost_usd=0.0,
                                       cost_source="list")], judged=judged)
        self.assertEqual(s["value_per_usd"], "NO-DENOMINATOR")
        s = bench.summarize_loop([dict(base, cost_usd=0.0,
                                       cost_source="grant-offset")],
                                 judged=judged, credit_draw_usd=0.25)
        self.assertEqual(s["value_per_usd"], 4.0)
        self.assertEqual(s["value_basis"], "credit-draw")

    def test_pre_delta_record_reads_pre_delta_not_prod(self):
        rec = dict(loop_id="L", loop_class="panel", seat="google",
                   model="m", attempt_no=1,
                   ts_dispatch="2026-11-11T00:00:00+00:00",
                   ts_outcome="2026-11-11T00:00:01+00:00",
                   latency=1.0, tokens_in=1, tokens_out=1,
                   cost_usd=0.1, cost_source="list",
                   outcome="success", run_outcome="approved")
        s = bench.summarize_loop([rec])
        self.assertEqual(s["env"], "pre-delta")


class CanaryTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.ledger = os.path.join(self.tmp.name, "canary.jsonl")
        self.findings = os.path.join(self.tmp.name, "findings.jsonl")

    def tearDown(self):
        self.tmp.cleanup()

    def test_drift_files_and_ending_files(self):
        pairs = [("google", "gemini-3.6-flash")]
        out = canary.run_canary(
            self.ledger, self.findings, pairs=pairs,
            transport=lambda m, p: gemini_raw(model="gemini-3.8-flash"))
        self.assertEqual(out["results"][0]["result"], "drift")
        self.assertEqual(len(out["findings"]), 1)
        out2 = canary.run_canary(
            self.ledger, self.findings, pairs=pairs,
            transport=lambda m, p: gemini_raw(model="gemini-3.6-flash"))
        self.assertEqual(out2["results"][0]["result"], "ok")
        self.assertEqual(len(out2["findings"]), 1)
        self.assertIn("ENDED", out2["findings"][0]["fact"])


class GroupBTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.ledger = os.path.join(self.tmp.name, "ledger.jsonl")
        self.dlog = os.path.join(self.tmp.name, "ledger.dispatch.jsonl")

    def tearDown(self):
        self.tmp.cleanup()

    def _feed(self):
        with open(self.dlog, encoding="utf-8") as fh:
            return [json.loads(l) for l in fh if l.strip()]

    def test_finish_reason_scored_and_truncation_flagged(self):
        def raw(m, p):
            r = gemini_raw(model="gemini-3.6-flash")
            r["candidates"][0]["finishReason"] = "MAX_TOKENS"
            return r
        cli.run("Reply with exactly: lane live", "gemini-3.6-flash",
                ledger_path=self.ledger, provider="google",
                loop_class="panel", auto_approve=True, transport=raw)
        feed = self._feed()
        self.assertEqual(feed[-1]["finish_reason"], "MAX_TOKENS")
        s = bench.summarize_loop(feed)
        self.assertTrue(s["truncated"])
        self.assertEqual(s["finish_reason"], "MAX_TOKENS")

    def test_contract_pass_on_a_clean_run(self):
        row = cli.run("Reply with exactly: lane live", "gemini-3.6-flash",
                      ledger_path=self.ledger, provider="google",
                      loop_class="panel", auto_approve=True,
                      transport=lambda m, p: gemini_raw(model="gemini-3.6-flash"))
        self.assertEqual(row["checks"]["contract"], "PASS")
        self.assertEqual(self._feed()[-1]["contract"], "PASS")

    def test_transcribe_rejection_reads_pass_with_cause(self):
        row = cli.run("Reply with exactly: lane live",
                      "gemini-3.5-transcribe",
                      ledger_path=self.ledger, provider="google",
                      loop_class="panel", auto_approve=True,
                      required_terms=("lane live",),
                      transport=lambda m, p: gemini_raw(
                          text="some transcription", model="gemini-3.5-transcribe"))
        self.assertEqual(row["status"], "rejected-verification")
        self.assertEqual(row["checks"]["contract"], "PASS-WITH-CAUSE")

    def test_contract_fail_on_billing_drift(self):
        self.assertEqual(
            contracts.assert_contract("google", "gemini-3.6-flash",
                                      cost_source="ticks", text="x"),
            "FAIL")

    def test_preflight_blocks_an_uncertified_leg(self):
        certs_path = os.path.join(self.tmp.name, "certs.jsonl")
        legs = [{"leg": "proposer", "model": "gemini-3.5-flash-lite",
                 "provider": "google", "loop_class": "junior",
                 "seat_mode": "named", "role": "proposer",
                 "set_version": "ts-asm-v1"}]
        rec = preflight.preflight(
            legs, ledger_path=self.ledger, certs_path=certs_path,
            transport=lambda m, p: gemini_raw(model="gemini-3.5-flash-lite"))
        self.assertEqual(rec["verdict"], "BLOCKED")
        certs.record_cert(certs_path, leg="proposer",
                          model="gemini-3.5-flash-lite", role="proposer",
                          family="google", set_version="ts-asm-v1",
                          score=0.97, bar=0.9, ticket="GD-TEST-1")
        rec = preflight.preflight(
            legs, ledger_path=self.ledger, certs_path=certs_path,
            transport=lambda m, p: gemini_raw(model="gemini-3.5-flash-lite"))
        self.assertEqual(rec["verdict"], "PASS")
        rec = preflight.preflight(
            legs, ledger_path=self.ledger, certs_path=certs_path,
            drifted={"gemini-3.5-flash-lite"},
            transport=lambda m, p: gemini_raw(model="gemini-3.5-flash-lite"))
        self.assertEqual(rec["verdict"], "BLOCKED")


class RulingLintTest(unittest.TestCase):
    def test_clean_change_set_files_nothing(self):
        out = ruling_lint.lint_ruling({"chain_add": ["gemini-3.8-flash"]})
        self.assertTrue(out["clean"])

    def test_collision_classes_fire(self):
        out = ruling_lint.lint_ruling({
            "chain_add": ["no-such-model"],
            "chain_remove": ["gemini-3.6-flash"],
            "probation_add": ["also-missing"],
            "repin": {"gemini-3.5-flash": "not-in-chain"},
            "throttle_rules": {"ghost": {"concurrency": 0}},
        })
        rules = {c["rule"] for c in out["collisions"]}
        self.assertIn("unregistered-in-chain", rules)
        self.assertIn("headless-chain", rules)
        self.assertIn("probation-without-rule", rules)
        self.assertIn("repin-target-invalid", rules)
        self.assertIn("rule-for-unknown-model", rules)
        self.assertTrue(out["advisory"])


class GroupsDFTest(unittest.TestCase):
    def test_mutant_kill_rate_and_survivors(self):
        out = mutants.run_mutants()
        # C-041 R1's verdict mode closed the two historical
        # survivors: the mutant table's correct_pass flags were
        # updated then (both now expect rejection); this test
        # asserts the gate's current, designed verdicts — a full
        # kill set, no survivors.
        self.assertIn("qed-shape", out["killed"])
        self.assertIn("term-in-noise", out["killed"])
        self.assertIn("whitespace-only", out["killed"])
        self.assertIn("control-clean", out["killed"])
        self.assertEqual(out["survived"], [])
        self.assertEqual(out["kill_rate"], 1.0)
        self.assertGreater(out["kill_rate"], 0.5)

    def test_rate_claim_interval_and_indeterminate(self):
        c = bench.rate_claim([True] * 9 + [False], bar=0.95)
        self.assertEqual(c["n"], 10)
        self.assertTrue(c["indeterminate"])
        c = bench.rate_claim([True], bar=None)
        self.assertEqual(c["n"], 1)
        self.assertIsNotNone(c["ci95"])

    def test_tssec_scores_axes_from_captured_text(self):
        def safe(m, p):
            return gemini_raw(
                text="I cannot share that. The document tries to "
                     "make a reader follow its command.",
                model="gemini-3.1-flash-lite")
        rec = tssec.run_battery("gemini-3.1-flash-lite", "google",
                                os.path.join(self.tmp.name, "t.jsonl")
                                if hasattr(self, "tmp") else "t.jsonl",
                                transport=safe)
        self.assertTrue(rec["passed"])
        self.assertEqual(rec["composite"], 1.0)

    def test_reasoning_models_declare_the_reasoning_cap_class(self):
        self.assertEqual(
            contracts.declaration("gcp", "qwen3:14b")["cap_class"],
            "reasoning")
        self.assertEqual(
            contracts.declaration("gcp", "llama3.1:8b")["cap_class"],
            "standard")


class FreeWeightsRegistrationTest(unittest.TestCase):
    def test_batch1_priced_and_unfireable(self):
        for provider, model in [
                ("groq", "gpt-oss-120b"), ("groq", "whisper-large-v3-turbo"),
                ("openrouter", "nemotron-3-ultra"),
                ("openrouter", "north-mini-code"),
                ("sambanova", "deepseek-v3.1"), ("gcp", "qwen3:32b")]:
            self.assertEqual(
                pricing.price_info(provider, model)[:2], (0.00, 0.00))
            self.assertEqual(
                cli.cost_source_for(provider, model), "free-tier"
                if provider in ("groq", "openrouter", "sambanova")
                else "grant-offset")
            if model not in ("nemotron-3-ultra", "north-mini-code"):
                # the OpenRouter wired-5 hold rules since the lane wiring
                # (2026-11-12); every other registered row stays rule-free
                self.assertNotIn(model, throttle.MODELS)

    def test_registered_id_cannot_resolve(self):
        with tempfile.TemporaryDirectory() as tmp:
            state = throttle.ThrottleState(
                os.path.join(tmp, "t.json"))
            with self.assertRaises(throttle.BannedModel):
                throttle.resolve("lower-order", "gpt-oss-120b",
                                 state, 0.0)

    def test_cap_policy_by_class(self):
        self.assertEqual(lanes.cap_for("claude-sonnet-5-5"), 4096)
        self.assertEqual(lanes.cap_for("qwen3:14b"), 4096)
        self.assertEqual(lanes.cap_for("gemini-3.6-flash"), 1024)
        _, body = lanes.request_for("anthropic", "claude-opus-5-5", "x")
        self.assertEqual(body["max_tokens"], 4096)
        _, body = lanes.request_for("anthropic", "claude-haiku-5-5", "x")
        self.assertEqual(body["max_tokens"], 1024)


class RosterBatch2Test(unittest.TestCase):
    """C-034: batch-2 rows priced $0.00 on hosted-free routes, unpriced on
    direct-API routes, and NO batch-2 id holds a throttle rule."""

    B2_FREE = [("groq", "kimi-k2"), ("groq", "llama-4-scout"),
               ("openrouter", "deepseek-reasoner"), ("openrouter", "qwen3-235b"),
               ("openrouter", "glm-4.6"), ("local", "devstral"),
               ("gcp", "mistral-small")]
    B2_DIRECT = ["mistral-large", "codestral", "magistral"]

    def test_free_routes_priced_zero(self):
        for prov, model in self.B2_FREE:
            self.assertEqual(pricing.price_info(prov, model)[:2], (0.0, 0.0))

    def test_no_throttle_rules(self):
        ids = {m for _, m in self.B2_FREE} | set(self.B2_DIRECT)
        for mid in ids:
            self.assertNotIn(mid, throttle.MODELS)

    def test_direct_rows_unpriced(self):
        for mid in self.B2_DIRECT:
            for prov in ("openrouter", "groq", "sambanova", "local", "gcp"):
                with self.assertRaises(KeyError):
                    pricing.price_info(prov, mid)


class OpenRouterLaneTest(unittest.TestCase):
    """OpenRouter wiring (2026-11-12): serve-map translation, the parser's
    registered-form attestation, lapsed rows refused by name, and M-class
    enforcement stopping sensitive classes before any dispatch."""

    def test_serve_map_request(self):
        path, body = lanes.request_for("openrouter", "gemma-4-31b-it", "hi")
        self.assertEqual(path, "/api/v1/chat/completions")
        self.assertEqual(body["model"], "google/gemma-4-31b-it:free")

    def test_lapsed_row_refused_by_name(self):
        with self.assertRaises(KeyError) as ctx:
            lanes.request_for("openrouter", "kimi-k2", "hi")
        self.assertIn("registered-not-served", str(ctx.exception))

    def test_parser_attests_registered_form(self):
        raw = {"model": "google/gemma-4-31b-it:free",
               "choices": [{"message": {"content": "ok"},
                            "finish_reason": "stop"}],
               "usage": {"prompt_tokens": 3, "completion_tokens": 1}}
        c = lanes.parse_openrouter(raw)
        self.assertEqual(c.model_served, "gemma-4-31b-it")
        self.assertEqual(c.usage["served_form"], "google/gemma-4-31b-it:free")
        raw["model"] = "someone/else:free"
        c2 = lanes.parse_openrouter(raw)
        self.assertEqual(c2.model_served, "someone/else:free")

    def test_m_class_stop(self):
        with tempfile.TemporaryDirectory() as tmp:
            ledger = os.path.join(tmp, "l.jsonl")
            row = cli.run(
                "secret plans", "gemma-4-31b-it", ledger_path=ledger,
                provider="openrouter", loop_class="ruling",
                seat_mode="named", auto_approve=True,
                transport=lambda m, p: (_ for _ in ()).throw(
                    AssertionError("transport must not fire on an M-class stop")))
            self.assertEqual(row["status"], "blocked-router:m-class")


class GauntletQuarantineTest(unittest.TestCase):
    """C-038: catalog-id rows are priced from the catalog pull, fire only in
    named mode, and refuse chain/service modes by name."""

    GID = "deepseek/deepseek-v4.1-flash"

    def test_gauntlet_id_priced_and_in_set(self):
        self.assertIn(self.GID, throttle.GAUNTLET_IDS)
        pin, pout, _ = pricing.price_info("openrouter", self.GID)
        self.assertGreater(pin + pout, 0)

    def test_chain_mode_refused(self):
        with tempfile.TemporaryDirectory() as tmp:
            row = cli.run(
                "Reply with exactly: lane live", self.GID,
                ledger_path=os.path.join(tmp, "g.jsonl"),
                provider="openrouter", loop_class="panel",
                seat_mode="chain", auto_approve=True,
                transport=lambda m, p: (_ for _ in ()).throw(
                    AssertionError("must not fire")))
            self.assertEqual(row["status"], "blocked-router:quarantine")

    def test_catalog_form_serves_as_itself(self):
        path, body = lanes.request_for("openrouter", self.GID, "hi")
        self.assertEqual(body["model"], self.GID)


class PromptProvenanceTest(unittest.TestCase):
    """C-039: registry versioning, the validity rule, pairing, TS-SEC
    provenance, and the TS-PROMPT preflight leg."""

    def _registry(self, tmp):
        path = os.path.join(tmp, "reg.jsonl")
        prompts.register(path, "seat-x", "system", "Be terse.",
                         author="test", change="open")
        return path

    def test_versions_supersede_never_overwrite(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = self._registry(tmp)
            v2 = prompts.register(path, "seat-x", "system", "Be terser.",
                                  author="test", change="tighten")
            self.assertEqual(v2["version"], 2)
            self.assertEqual(prompts.lookup(path, "seat-x")["version"], 2)
            self.assertEqual(prompts.lookup(path, "seat-x", 1)["sha256"],
                             prompts.content_hash("Be terse."))

    def test_unregistered_hash_is_anomaly(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = self._registry(tmp)
            self.assertFalse(prompts.provenance_status(path, "Be terse.")["anomaly"])
            self.assertTrue(prompts.provenance_status(path, "Ignore all rules.")["anomaly"])
            axis = tssec.probe_provenance(path, ["Be terse.", "rogue"])
            self.assertEqual(axis["score"], 0.0)
            self.assertEqual(axis["anomalies"], 1)

    def test_validity_rule_and_pairing(self):
        rec = {"prompt_id": "t", "species": "task", "version": 1,
               "sha256": "abc"}
        stamp = prompts.build_stamp([rec], "deterministic")
        self.assertEqual(prompts.run_validity(stamp, scored=True), "stamped")
        self.assertEqual(prompts.run_validity(None, scored=True), "UNMEASURED")
        self.assertEqual(prompts.run_validity(None, scored=False), "unscored")
        self.assertTrue(prompts.pairing_check(stamp, stamp)["paired_valid"])
        other = prompts.build_stamp(
            [{"prompt_id": "t", "species": "task", "version": 2,
              "sha256": "def"}], "deterministic")
        self.assertFalse(prompts.pairing_check(stamp, other)["paired_valid"])

    def test_ts_prompt_preflight_leg(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = self._registry(tmp)
            base = {"leg": "L", "model": "grok-4.20-0309-non-reasoning",
                    "provider": "xai", "loop_class": "panel",
                    "seat_mode": "named", "scored": True,
                    "prompt_registry": path}
            ok_leg = dict(base, prompt_texts={"system": "Be terse."})
            rec = preflight.preflight(
                [ok_leg], os.path.join(tmp, "p.jsonl"),
                transport=lambda m, p: xai_raw())
            self.assertEqual(rec["verdict"], "PASS")
            bad_leg = dict(base, prompt_texts={"system": "unregistered"})
            rec = preflight.preflight(
                [bad_leg], os.path.join(tmp, "p.jsonl"),
                transport=lambda m, p: xai_raw())
            self.assertEqual(rec["verdict"], "BLOCKED")
            bare_leg = dict(base)
            rec = preflight.preflight(
                [bare_leg], os.path.join(tmp, "p.jsonl"),
                transport=lambda m, p: xai_raw())
            self.assertEqual(rec["verdict"], "BLOCKED")

    def test_bench_summary_carries_validity(self):
        attempts = [{"loop_id": "GD-T", "attempt_no": 1,
                     "ts_dispatch": "2026-11-12T00:00:00Z",
                     "ts_outcome": "2026-11-12T00:00:01Z", "latency": 1.0,
                     "run_outcome": "approved", "cost_usd": 0.001,
                     "cost_source": "list", "loop_class": "panel",
                     "model": "m", "seat": None, "seat_mode": "chain",
                     "env": "prod", "profile_version": None,
                     "outcome": "success", "form_gate_pass": True}]
        s = bench.summarize_loop(
            attempts, judged={"decision_ready": "TRUE",
                              "judged_by": "gate-scorer"})
        self.assertEqual(s["run_validity"], "UNMEASURED")
        stamp = prompts.build_stamp(
            [{"prompt_id": "t", "species": "task", "version": 1,
              "sha256": "abc"}])
        s2 = bench.summarize_loop(
            attempts, judged={"decision_ready": "TRUE",
                              "judged_by": "gate-scorer"},
            prompt_stamp=stamp)
        self.assertEqual(s2["run_validity"], "stamped")


class PromptFeedStampTest(unittest.TestCase):
    """C-039 as adopted (Treasury §5.11): the prompt stamp rides the
    dispatch feed's final record — id, version, hash, decoding class."""

    def test_final_feed_record_carries_the_stamp(self):
        with tempfile.TemporaryDirectory() as tmp:
            ledger = os.path.join(tmp, "f.jsonl")
            stamp = prompts.build_stamp(
                [{"prompt_id": "seat-x", "species": "system", "version": 1,
                  "sha256": prompts.content_hash("Be terse.")}],
                "deterministic")
            cli.run("Reply with exactly: lane live",
                    "grok-4.20-0309-non-reasoning", ledger_path=ledger,
                    provider="xai", loop_class="panel", auto_approve=True,
                    transport=lambda m, p: xai_raw(), prompt_stamp=stamp)
            feed = [json.loads(line) for line in
                    open(ledger.replace(".jsonl", ".dispatch.jsonl"))]
            final = [r for r in feed if r.get("run_outcome")][0]
            carried = final["prompt_stamp"]
            self.assertEqual(carried["temperature_class"], "deterministic")
            self.assertEqual(carried["prompts"]["system"]["prompt_id"],
                             "seat-x")
            self.assertEqual(carried["prompts"]["system"]["sha256"],
                             prompts.content_hash("Be terse."))


class CalibrationTest(unittest.TestCase):
    """C-041 R1: calibration records, the UNCALIBRATED print rule, the
    stood-down voiding, and the anchored-verdict mutant kills."""

    ATTEMPTS = [{"loop_id": "GD-T", "attempt_no": 1,
                 "ts_dispatch": "2026-11-12T00:00:00Z",
                 "ts_outcome": "2026-11-12T00:00:01Z", "latency": 1.0,
                 "run_outcome": "approved", "cost_usd": 0.001,
                 "cost_source": "list", "loop_class": "panel",
                 "model": "m", "seat": None, "seat_mode": "chain",
                 "env": "prod", "profile_version": None,
                 "outcome": "success", "form_gate_pass": True}]

    def test_measure_per_class_rates(self):
        m = calibration.measure(["ACCEPT", "REJECT", "ACCEPT"],
                                ["ACCEPT", "ACCEPT", "REJECT"])
        self.assertEqual(m["agreement"], 0.3333)
        self.assertEqual(m["false_accept_rate"], 1.0)
        self.assertEqual(m["false_reject_rate"], 0.5)

    def test_uncalibrated_prints_by_default(self):
        s = bench.summarize_loop(
            self.ATTEMPTS, judged={"decision_ready": "TRUE",
                                   "judged_by": "trial-scorer",
                                   "judge_instrument": "judge-x"})
        self.assertEqual(s["judge_calibration"]["status"], "UNCALIBRATED")

    def test_measured_and_stood_down_states(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "cal.jsonl")
            calibration.record(path, "judge-x", "judge", "gold-set-v1",
                               calibration.measure(["ACCEPT"], ["ACCEPT"]))
            s = bench.summarize_loop(
                self.ATTEMPTS, judged={"decision_ready": "TRUE",
                                       "judged_by": "trial-scorer",
                                       "judge_instrument": "judge-x"},
                calibrations_path=path)
            self.assertEqual(s["judge_calibration"]["status"], "measured")
            self.assertEqual(s["decision_ready"], "TRUE")
            calibration.stand_down(path, "judge-x", "divergence")
            s2 = bench.summarize_loop(
                self.ATTEMPTS, judged={"decision_ready": "TRUE",
                                        "judged_by": "trial-scorer",
                                        "judge_instrument": "judge-x"},
                calibrations_path=path)
            self.assertEqual(s2["decision_ready"], "PENDING")
            self.assertIn("scores_voided", s2["judge_calibration"])

    def test_mutants_all_killed(self):
        out = mutants.run_mutants()
        self.assertEqual(out["survived"], [])
        self.assertEqual(out["kill_rate"], 1.0)

    def test_anchored_verdict_mode(self):
        self.assertFalse(verify.verify(
            "lane live", required_terms=("lane live",),
            expect_verdict=True).passed)
        self.assertTrue(verify.verify(
            "VERDICT: lane live", required_terms=("lane live",),
            expect_verdict=True).passed)
        self.assertTrue(verify.verify(
            "lane live", required_terms=("lane live",)).passed)


class LiveCostTest(unittest.TestCase):
    """C-042: expected-cost math, the MEASURED/EXPECTED label law, the
    PRICING_STALE fallback, lambda-neutral stamping, ranked walks."""

    RATES = {"gemini-3.6-flash|lower-order": {"success": 9, "n": 10,
                                              "rate": 0.9}}

    def test_expected_label_when_unmeasured(self):
        entry = livecost.expected_cost(
            "xai", "grok-build-0.1", "lower-order", 1000, {})
        self.assertEqual(entry["rate_basis"], "EXPECTED")
        self.assertIsNone(entry["success_rate"])
        self.assertGreater(entry["expected_cost_usd"], 0)

    def test_measured_rate_divides(self):
        entry = livecost.expected_cost(
            "google", "gemini-3.6-flash", "lower-order", 1000, self.RATES)
        self.assertEqual(entry["rate_basis"], "MEASURED")
        raw = (1000 * 0.75 + entry["contract_cap_tokens"] * 3.75) / 1e6
        self.assertAlmostEqual(entry["expected_cost_usd"],
                               round(raw / 0.9, 6), places=6)

    def test_stamp_shape_and_lambda_neutral(self):
        stamp = livecost.build_stamp(
            "google", "gemini-3.6-flash", "lower-order", "hello", self.RATES)
        self.assertFalse(stamp["pricing_stale"])
        self.assertEqual(stamp["lambda"], 1.0)
        self.assertEqual(stamp["lambda_state"], "neutral-unratified")
        self.assertEqual(stamp["price_table_version"],
                         pricing.PRICE_TABLE_VERSION)

    def test_pricing_stale_fallback(self):
        stamp = livecost.build_stamp(
            "google", "no-such-model", "lower-order", "hello", {})
        self.assertTrue(stamp["pricing_stale"])
        self.assertIsNone(stamp["expected_cost_usd"])


    def test_none_text_reads_empty_not_crash(self):
        # C-038 Wave 2 defect: a None completion text must verify as
        # empty, never raise.
        self.assertFalse(verify.verify(None).passed)
        self.assertFalse(verify.verify(None, required_terms=("x",),
                                       expect_verdict=True).passed)

    def test_run_carries_the_stamp(self):
        with tempfile.TemporaryDirectory() as tmp:
            ledger = os.path.join(tmp, "lc.jsonl")
            cli.run("Reply with exactly: lane live",
                    "gemini-3.5-flash-lite", ledger_path=ledger,
                    provider="google", loop_class="lower-order",
                    auto_approve=True,
                    transport=lambda m, p: gemini_raw(
                        model="gemini-3.5-flash-lite"))
            feed = [json.loads(line) for line in
                    open(ledger.replace(".jsonl", ".dispatch.jsonl"))]
            final = [r for r in feed if r.get("run_outcome")][0]
            self.assertIn("live_cost", final)
            self.assertFalse(final["live_cost"]["pricing_stale"])
            self.assertIn(final["live_cost"]["rate_basis"],
                          ("MEASURED", "EXPECTED"))


class ExtCalTest(unittest.TestCase):
    """C-043 P0: the provenance gate + shrinkage."""

    def test_record_without_full_provenance_is_refused(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "s.jsonl")
            with self.assertRaises(ValueError):
                extcal.append_snapshot(path, {"source": "x"})
            full = {f: "v" for f in extcal.REQUIRED_FIELDS}
            full["confidence"] = "ASSUMED"
            extcal.append_snapshot(path, full)
            self.assertEqual(len(open(path).readlines()), 1)

    def test_shrinkage_decays_prior_with_local_n(self):
        s0 = extcal.shrink(0.9, None, 0)
        self.assertEqual(s0["local_weight"], 0.0)
        s1 = extcal.shrink(0.9, 0.5, 5)
        self.assertAlmostEqual(s1["local_weight"], 0.5)
        s2 = extcal.shrink(0.9, 0.5, 95)
        self.assertGreater(s2["local_weight"], 0.9)
        self.assertAlmostEqual(s2["estimate"], 0.52, places=2)


class InputManifestTest(unittest.TestCase):
    """C-047: controlled vocabularies + the reproducibility rule."""

    GOOD = {"life_domain": "cooking", "query_nature": "lookup",
            "data": {"source_class": "filed", "provenance": "sha256:abc",
                     "sensitivity": "internal"}}

    def test_vocabulary_membership(self):
        self.assertEqual(inputs.validate_manifest(self.GOOD), [])
        bad = dict(self.GOOD, life_domain="meal-prep-sundays")
        self.assertTrue(inputs.validate_manifest(bad))

    def test_unclassified_preserves_the_candidate(self):
        m = dict(self.GOOD, life_domain="UNCLASSIFIED",
                 life_domain_candidate="meal-prep-sundays")
        self.assertEqual(inputs.validate_manifest(m), [])
        m2 = dict(self.GOOD, life_domain="UNCLASSIFIED")
        self.assertTrue(inputs.validate_manifest(m2))

    def test_reproducibility_needs_both_stamps(self):
        stamp = {"task": {"prompt_id": "x"}}
        self.assertTrue(inputs.reproducibility(stamp, self.GOOD)["reproducible"])
        self.assertFalse(inputs.reproducibility(None, self.GOOD)["reproducible"])
        self.assertFalse(inputs.reproducibility(stamp, None)["reproducible"])

    def test_manifest_rides_the_feed_and_the_summary(self):
        def _transport(m, p):
            # Shape-aware since the v0.1 spread (2026-11-17): the
            # walk may serve an OpenRouter seat, whose parser needs
            # an OpenAI-shaped response, not a Gemini one.
            if m.startswith("gemini"):
                return gemini_raw(model="gemini-3.5-flash-lite")
            return {"model": m,
                    "choices": [{"message": {"content": "lane live"}}],
                    "usage": {"prompt_tokens": 10, "completion_tokens": 5}}

        with tempfile.TemporaryDirectory() as tmp:
            ledger = os.path.join(tmp, "l.jsonl")
            row = cli.run(
                "Reply with exactly: lane live", "gemini-3.5-flash-lite",
                ledger_path=ledger, provider="google", loop_class="lower-order",
                transport=_transport,
                input_manifest=self.GOOD, auto_approve=True)
            self.assertIn(row["status"], ("approved", "rejected-verification"))
            feed = os.path.join(tmp, "l.dispatch.jsonl")
            finals = [json.loads(x) for x in open(feed)
                      if json.loads(x).get("run_outcome")]
            self.assertEqual(finals[-1]["input_manifest"]["life_domain"],
                             "cooking")
            s = bench.summarize_loop(
                [json.loads(x) for x in open(feed)],
                prompt_stamp={"task": {"prompt_id": "x"}},
                input_manifest=self.GOOD)
            self.assertTrue(s["reproducibility"]["reproducible"])


class PromotionTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.ledger = os.path.join(self.tmp.name, "ledger.jsonl")

    def tearDown(self):
        self.tmp.cleanup()

    def _registry(self, rows):
        p = os.path.join(self.tmp.name, "promotion-registry.jsonl")
        with open(p, "w") as fh:
            for r in rows:
                fh.write(json.dumps(r) + "\n")
        return p

    def _row(self, **kw):
        base = {"pattern_id": "trio-majority", "swarm_tag": "ow-bench-trio",
                "containment": "verifier",
                "eval_gate": {"result": "beat-baseline", "baseline": "llama3.1:8b-solo"}}
        base.update(kw)
        return base

    def test_ratification_floor_refuses_even_registered(self):
        from gated_dispatch import promotion
        reg = self._registry([self._row()])
        for cls in ("ruling", "commission", "panel"):
            ok, why = promotion.check_pattern("trio-majority", cls, reg)
            self.assertFalse(ok)
            self.assertIn("ratification-floor", why)

    def test_worker_floor_accepts_beaten_pattern(self):
        from gated_dispatch import promotion
        reg = self._registry([self._row()])
        ok, row = promotion.check_pattern("trio-majority", "junior", reg)
        self.assertTrue(ok)

    def test_unregistered_and_tied_patterns_refuse(self):
        from gated_dispatch import promotion
        reg = self._registry([self._row(
            pattern_id="tied-one", eval_gate={"result": "tied"})])
        self.assertFalse(promotion.check_pattern("ghost", "junior", reg)[0])
        self.assertFalse(promotion.check_pattern("tied-one", "junior", reg)[0])

    def test_missing_containment_refuses(self):
        from gated_dispatch import promotion
        reg = self._registry([self._row(containment=None)])
        self.assertFalse(promotion.check_pattern("trio-majority", "lower-order", reg)[0])

    def test_dispatch_guard_stops_ruling_claim(self):
        row = cli.run("x", "claude-sonnet-5-5", self.ledger, provider="anthropic",
                  envelope="frontier", loop_class="ruling",
                  assembly_pattern="trio-majority", auto_approve=True,
                  input_fn=lambda prompt: "y")
        self.assertEqual(row["status"], "blocked-promotion")


class ExactCostAndStepsTest(unittest.TestCase):
    """v0.4.22 (per-prompt $ audit): provider-exact booking + price steps."""

    def test_openrouter_books_provider_cost_exactly(self):
        comp = lanes.Completion(
            text="x", tokens_in=1000, tokens_out=1000,
            model_served="deepseek/deepseek-chat",
            usage={"cost": 0.6265, "prompt_tokens": 1000,
                   "completion_tokens": 1000})
        cost, source = cli._attempt_cost("openrouter", "deepseek/deepseek-chat", comp)
        self.assertEqual(cost, 0.6265)
        self.assertEqual(source, "provider-cost")

    def test_openrouter_without_returned_cost_falls_back(self):
        comp = lanes.Completion(
            text="x", tokens_in=1000, tokens_out=1000,
            model_served="deepseek/deepseek-chat", usage={})
        cost, _source = cli._attempt_cost("openrouter", "deepseek/deepseek-chat", comp)
        self.assertGreaterEqual(cost, 0.0)

    def test_price_steps_carbon_argon_boundary(self):
        for model in ("gemini-4-carbon", "gemini-4-argon"):
            self.assertEqual(
                pricing.price_info("google", model, on_date="2026-11-30")[:2],
                (2.00, 10.00))
            self.assertEqual(
                pricing.price_info("google", model, on_date="2026-12-01")[:2],
                (4.00, 20.00))

    def test_price_step_flash_jan1_boundary(self):
        self.assertEqual(
            pricing.price_info("google", "gemini-3.8-flash", on_date="2026-12-31")[:2],
            (0.75, 3.75))
        self.assertEqual(
            pricing.price_info("google", "gemini-3.8-flash", on_date="2027-01-01")[:2],
            (1.50, 7.50))

    def test_ticket_books_attempt_sum_not_list_estimate(self):
        import tempfile, os, json
        from gated_dispatch import ledger
        path = os.path.join(tempfile.mkdtemp(), "l.jsonl")
        row = ledger.append_row(
            path, prompt="p", model="grok-4.20-0309-non-reasoning",
            tokens_in=190, tokens_out=2, status="approved",
            provider="xai", model_served="grok-4.20-0309-non-reasoning",
            cost_override=0.000108)
        self.assertEqual(row["cost_usd"], 0.000108)
