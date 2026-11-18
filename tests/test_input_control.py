"""E-1 input-side control (ratified 2026-11-17; I&A Finding F-20).

Two legs: (1) a routed run on a judgment-bearing class
(qr-commission-ruling, qr-panel-verdict) must carry a valid C-047
input manifest — absent refuses blocked-input:manifest-required,
invalid refuses blocked-input:manifest-invalid, both before any
provider call; non-judgment classes are untouched. (2) The
masking seam resolves its register per run and stamps its state
on every ticket: active with counts when a register resolves,
active=False when none does.
"""

import json
import os
import tempfile
import unittest
from unittest import mock

from gated_dispatch import cli, masking, prompts


GOOD = {"life_domain": "cooking", "query_nature": "lookup",
        "data": {"source_class": "filed", "provenance": "sha256:abc",
                 "sensitivity": "internal"}}


def _transport(model, prompt):
    return {"choices": [{"message": {"content": "lane live"}}],
            "usage": {"prompt_tokens": 10, "completion_tokens": 2}}


def _boom(model, prompt):
    raise AssertionError("transport must not fire on a refusal")


class JudgmentManifestTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.ledger = os.path.join(self.tmp.name, "ledger.jsonl")
        env = mock.patch.dict(os.environ, {}, clear=False)
        env.start()
        os.environ.pop("GD_MASKING_REGISTER", None)
        # v0.3 priming wrap: the approved routed runs in this class
        # carry a verified fixture stamp.
        reg = os.path.join(self.tmp.name, "registry.jsonl")
        rec = prompts.register(reg, "fx-priming", "task",
                               "fixture priming text", "test",
                               "v0.3 priming fixture")
        self.stamp = prompts.build_stamp([rec])
        os.environ["GD_PROMPT_REGISTRY"] = reg
        self.addCleanup(env.stop)
        self.addCleanup(self.tmp.cleanup)

    def run_gate(self, **kw):
        kw.setdefault("ledger_path", self.ledger)
        kw.setdefault("envelope", "frontier")
        kw.setdefault("auto_approve", True)
        kw.setdefault("prompt_stamp", self.stamp)
        return cli.run(**kw)

    def test_judgment_class_without_manifest_refuses(self):
        row = self.run_gate(
            prompt="Reply with exactly: lane live",
            model="gemini-3.6-flash", provider="google",
            loop_class="panel", routing_class="qr-panel-verdict",
            transport=_boom)
        self.assertEqual(row["status"], "blocked-input:manifest-required")
        self.assertEqual(row["cost_usd"], 0.0)

    def test_commission_class_without_manifest_refuses(self):
        row = self.run_gate(
            prompt="Reply with exactly: lane live",
            model="claude-opus-5-5", provider="anthropic",
            loop_class="commission",
            routing_class="qr-commission-ruling", transport=_boom)
        self.assertEqual(row["status"], "blocked-input:manifest-required")

    def test_judgment_class_with_valid_manifest_proceeds(self):
        row = self.run_gate(
            prompt="Reply with exactly: lane live",
            model="nemotron-3-ultra", provider="openrouter",
            loop_class="panel", routing_class="qr-panel-verdict",
            input_manifest=GOOD, transport=_transport,
            required_terms=("lane live",))
        self.assertEqual(row["status"], "approved")

    def test_judgment_class_with_invalid_manifest_refuses(self):
        bad = dict(GOOD, life_domain="meal-prep-sundays")
        row = self.run_gate(
            prompt="Reply with exactly: lane live",
            model="gemini-3.6-flash", provider="google",
            loop_class="panel", routing_class="qr-panel-verdict",
            input_manifest=bad, transport=_boom)
        self.assertEqual(row["status"], "blocked-input:manifest-invalid")

    def test_non_judgment_class_needs_no_manifest(self):
        row = self.run_gate(
            prompt="Reply with exactly: lane live",
            model="nemotron-3-ultra", provider="openrouter",
            loop_class="lower-order", routing_class="qr-research",
            transport=_transport, required_terms=("lane live",))
        self.assertEqual(row["status"], "approved")


class MaskingStampTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.ledger = os.path.join(self.tmp.name, "ledger.jsonl")
        self.addCleanup(self.tmp.cleanup)

    def feed_rows(self):
        path = self.ledger.replace(".jsonl", ".dispatch.jsonl")
        with open(path) as fh:
            return [json.loads(line) for line in fh if line.strip()]

    def test_stamp_records_inert_state_by_default(self):
        with mock.patch.dict(os.environ, {}, clear=False):
            os.environ.pop("GD_MASKING_REGISTER", None)
            with mock.patch.object(
                    masking, "resolve_register_path",
                    return_value=None):
                cli.run("Reply with exactly: lane live",
                        "nemotron-3-ultra", ledger_path=self.ledger,
                        provider="openrouter", envelope="frontier",
                        auto_approve=True, loop_class="lower-order",
                        transport=_transport,
                        required_terms=("lane live",))
        rows = [r for r in self.feed_rows() if r.get("masking")]
        self.assertTrue(rows)
        self.assertEqual(rows[-1]["masking"], {"active": False})

    def test_stamp_records_active_with_counts(self):
        register = {"always": [],
                    "names": {"Zanzibar Q Public": "Person_A"},
                    "name_parts": {}, "orgs": {}, "never": []}
        reg_path = os.path.join(self.tmp.name, "register.json")
        with open(reg_path, "w") as fh:
            json.dump(register, fh)
        with mock.patch.dict(os.environ,
                             {"GD_MASKING_REGISTER": reg_path}):
            cli.run("Mention Zanzibar Q Public here",
                    "nemotron-3-ultra", ledger_path=self.ledger,
                    provider="openrouter", envelope="frontier",
                    auto_approve=True, loop_class="lower-order",
                    transport=_transport)
        rows = [r for r in self.feed_rows() if r.get("masking")]
        self.assertTrue(rows)
        self.assertTrue(rows[-1]["masking"]["active"])
        self.assertEqual(rows[-1]["masking"]["counts"].get("name"), 1)

    def test_resolve_register_path_prefers_env(self):
        with mock.patch.dict(os.environ,
                             {"GD_MASKING_REGISTER": "/tmp/x.json"}):
            self.assertEqual(masking.resolve_register_path(),
                             "/tmp/x.json")


if __name__ == "__main__":
    unittest.main()
