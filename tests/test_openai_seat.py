"""OpenAI flagship voice (table v0.8, his commission 2026-11-19 via
Governance docket §128): admission as a flagship voice on the panel
and commission classes, the default flagship unchanged, and the
fail-closed masking guard on the seat."""
import os
import tempfile
import unittest

from gated_dispatch import cli, routing

GPT = ("openrouter", "openai/gpt-5.5")


def _or_raw(text="voice text"):
    return {"id": "chatcmpl-test", "model": "openai/gpt-5.5",
            "choices": [{"message": {"role": "assistant",
                                     "content": text}}],
            "usage": {"prompt_tokens": 40, "completion_tokens": 12,
                      "total_tokens": 52}}


def _transport(model, prompt):
    return _or_raw()


def _manifest(sensitivity):
    return {"life_domain": "UNCLASSIFIED",
            "life_domain_candidate": "operations",
            "query_nature": "judgment",
            "data": {"source_class": "filed",
                     "provenance": "test fixture",
                     "sensitivity": sensitivity}}


class FlagshipVoiceAdmissionTest(unittest.TestCase):
    def test_panel_verdict_admits_gpt_voice(self):
        d = routing.resolve("qr-panel-verdict", *GPT)
        self.assertTrue(d.allowed)
        self.assertEqual(d.stamp["position"], "flagship-voice")

    def test_commission_ruling_admits_gpt_voice(self):
        d = routing.resolve("qr-commission-ruling", *GPT)
        self.assertTrue(d.allowed)
        self.assertEqual(d.stamp["position"], "flagship-voice")

    def test_default_flagship_unchanged(self):
        stamp = routing.job_stamp("qr-commission-ruling")
        self.assertIn("claude-opus-5-5", stamp["selected"])
        stamp = routing.job_stamp("qr-panel-verdict")
        self.assertIn("gemini-3.6-flash", stamp["selected"])

    def test_gpt_voice_not_admitted_on_unrelated_class(self):
        d = routing.resolve("qr-draft-check", *GPT)
        self.assertFalse(d.allowed)

    def test_binding_row_present(self):
        rows = [b for b in routing.bindings_for("probabilistic")
                if b.model == "openai/gpt-5.5"]
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0].tier, "dispatchable")


class MaskingGuardTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.ledger = os.path.join(self.tmp.name, "t.jsonl")

    def tearDown(self):
        self.tmp.cleanup()

    def _run(self, **kw):
        base = dict(prompt="brief text", model="openai/gpt-5.5",
                    provider="openrouter", ledger_path=self.ledger,
                    seat_mode="named", auto_approve=True,
                    transport=_transport)
        base.update(kw)
        return cli.run(**base)

    def test_judgment_loop_unattested_refuses(self):
        t = self._run(loop_class="panel")
        self.assertEqual(t["status"], "blocked-masking:openai-seat")

    def test_judgment_loop_attested_fires(self):
        t = self._run(loop_class="panel", masking_attested=True)
        self.assertEqual(t["status"], "approved")

    def test_judgment_routing_class_unattested_refuses(self):
        t = self._run(loop_class="lower-order",
                      routing_class="qr-panel-verdict",
                      input_manifest=_manifest("internal"))
        self.assertEqual(t["status"], "blocked-masking:openai-seat")

    def test_sensitive_manifest_unattested_refuses_any_context(self):
        t = self._run(loop_class="lower-order",
                      input_manifest=_manifest("sensitive"))
        self.assertEqual(t["status"], "blocked-masking:openai-seat")

    def test_measurement_shape_unaffected(self):
        # The bake-off shape: named, lower-order, no manifest — fires.
        t = self._run(loop_class="lower-order")
        self.assertEqual(t["status"], "approved")

    def test_other_seats_unaffected(self):
        t = cli.run(prompt="brief", model="claude-opus-5-5",
                    provider="anthropic", ledger_path=self.ledger,
                    loop_class="panel", seat_mode="named",
                    auto_approve=True,
                    transport=lambda m, p: {
                        "id": "msg_t", "model": "claude-opus-5-5",
                        "content": [{"type": "text", "text": "ok"}],
                        "usage": {"input_tokens": 30,
                                  "output_tokens": 5}})
        self.assertEqual(t["status"], "approved")


if __name__ == "__main__":
    unittest.main()
