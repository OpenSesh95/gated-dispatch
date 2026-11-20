"""Router brain (v0.4.42) — the brain advises, the table governs.

Every test stubs cli.run: the suite never fires a live classification.
The stub also drives the parser-capture seam by writing the canned
completion text through lanes.PARSERS, exactly as a real parse would.
"""

import hashlib
import json
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from gated_dispatch import brain, lanes, prompts  # noqa: E402


class FakeCompletion:
    def __init__(self, text):
        self.text = text


class BrainHarness(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.registry = os.path.join(self.tmp, "registry.jsonl")
        prompts.register(self.registry, brain.PROMPT_ID, "system",
                         brain.PROMPT_TEXT, "gate-desk", "test row")
        self.ledger = os.path.join(self.tmp, "ledger.jsonl")
        self.calls = []

    def stub_run(self, text=None, outcome="approved", raises=False):
        def run(**kwargs):
            self.calls.append(kwargs)
            if raises:
                raise RuntimeError("transport down")
            # Feed the canned text through the (wrapped) parser seam.
            parser = lanes.PARSERS[brain.BRAIN_PROVIDER]
            parser({"choices": [{"message": {"content": text}}]})
            return {"status": outcome, "ticket": "GD-TEST-0001"}
        return run

    def classify(self, text="do a thing", stub=None, **kw):
        kw.setdefault("ledger_path", self.ledger)
        kw.setdefault("registry_path", self.registry)
        return brain.classify(text, run=stub or self.stub_run(
            '{"class": "qr-research", "nature": "probabilistic", '
            '"split": "spark", "dominant": null}'), **kw)


class TestBrainAdvises(BrainHarness):
    def test_valid_brain_answer_governs(self):
        out = self.classify()
        self.assertEqual(out["class"], "qr-research")
        self.assertEqual(out["source"], "brain")
        self.assertFalse(out["fallback"])
        self.assertEqual(out["split"], "spark")
        self.assertEqual(self.calls[0]["loop_class"], "router-brain")
        self.assertEqual(self.calls[0]["seat_mode"], "named")

    def test_prompt_hash_matches_catalogue(self):
        row = prompts.lookup(self.registry, brain.PROMPT_ID)
        digest = hashlib.sha256(brain.PROMPT_TEXT.encode()).hexdigest()
        self.assertEqual(row["sha256"], digest)


class TestFallbacks(BrainHarness):
    def test_unparseable_output_falls_back(self):
        out = self.classify(stub=self.stub_run("no json here"))
        self.assertEqual(out["class"], "qr-quick-lookup")
        self.assertTrue(out["fallback"])

    def test_unknown_class_falls_back(self):
        stub = self.stub_run('{"class": "qr-nope", "split": "claude", '
                             '"dominant": null}')
        out = self.classify(stub=stub)
        self.assertTrue(out["fallback"])

    def test_rejected_ticket_falls_back(self):
        stub = self.stub_run('{"class": "qr-research", "split": "claude",'
                             ' "dominant": null}', outcome="rejected-gate")
        out = self.classify(stub=stub)
        self.assertTrue(out["fallback"])

    def test_transport_exception_falls_back(self):
        out = self.classify(stub=self.stub_run(raises=True))
        self.assertTrue(out["fallback"])
        self.assertEqual(out["source"], "table-fallback")

    def test_unregistered_prompt_never_dispatches(self):
        empty = os.path.join(self.tmp, "empty.jsonl")
        open(empty, "w").close()
        out = self.classify(registry_path=empty)
        self.assertTrue(out["fallback"])
        self.assertEqual(self.calls, [])


class TestGuards(BrainHarness):
    def test_downgrade_of_judgment_class_refused(self):
        out = self.classify(stamper_class="qr-commission-ruling")
        self.assertEqual(out["class"], "qr-commission-ruling")
        self.assertTrue(out["downgrade_refused"])
        self.assertEqual(out["source"], "table-guarded")

    def test_downgrade_of_draft_check_refused(self):
        out = self.classify(stamper_class="qr-draft-check")
        self.assertEqual(out["class"], "qr-draft-check")
        self.assertTrue(out["downgrade_refused"])

    def test_brain_may_agree_with_guarded_class(self):
        stub = self.stub_run('{"class": "qr-panel-verdict", '
                             '"split": "claude", "dominant": null}')
        out = self.classify(stub=stub, stamper_class="qr-panel-verdict")
        self.assertEqual(out["source"], "brain")
        self.assertFalse(out["downgrade_refused"])

    def test_deterministic_class_never_dispatches(self):
        out = self.classify(stamper_class="qr-life-ops")
        self.assertEqual(out["class"], "qr-life-ops")
        self.assertEqual(out["source"], "table-deterministic")
        self.assertEqual(self.calls, [])

    def test_compartmented_never_dispatches(self):
        out = self.classify(sensitivity="compartmented")
        self.assertEqual(out["source"], "table-test0")
        self.assertTrue(out["fallback"])
        self.assertEqual(self.calls, [])


if __name__ == "__main__":
    unittest.main()
