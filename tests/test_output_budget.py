"""Output-budget transport parameter (v0.4.46): the council bench's
four GPT no-shows traced to the standard 1024 cap on a reasoning-first
seat. The cap classes now carry the OpenAI reasoning line, and an
explicit max_tokens threads cli.run -> lanes.dispatch -> the helper
request body."""
import os
import tempfile
import unittest

from gated_dispatch import cli, lanes


class CapClassTest(unittest.TestCase):
    def test_openai_reasoning_line_caps(self):
        self.assertEqual(lanes.cap_class_of("openai/gpt-5.5"),
                         "reasoning")
        self.assertEqual(lanes.cap_for("openai/gpt-5.5"), 4096)
        self.assertEqual(lanes.cap_for("openai/o3"), 4096)
        self.assertEqual(lanes.cap_class_of("openai/gpt-5.3-codex"),
                         "long-form")
        self.assertEqual(lanes.cap_for("openai/gpt-5.3-codex"), 4096)

    def test_standard_seats_unchanged(self):
        self.assertEqual(lanes.cap_for("gemini-3.6-flash"), 1024)
        self.assertEqual(lanes.cap_for("openai/gpt-5.4-nano"), 1024)

    def test_request_body_carries_cap_and_override(self):
        _, body = lanes.request_for("openrouter", "openai/gpt-5.5",
                                    "prompt")
        self.assertEqual(body["max_tokens"], 4096)
        _, body = lanes.request_for("openrouter", "openai/gpt-5.5",
                                    "prompt", max_tokens=6000)
        self.assertEqual(body["max_tokens"], 6000)
        _, body = lanes.request_for("anthropic", "claude-haiku-5-5",
                                    "prompt", max_tokens=777)
        self.assertEqual(body["max_tokens"], 777)


class RunKwargTest(unittest.TestCase):
    def test_run_accepts_max_tokens_with_stub_transport(self):
        tmp = tempfile.mkdtemp()
        ledger = os.path.join(tmp, "t.jsonl")
        t = cli.run(prompt="hi", model="openai/gpt-5.5",
                    provider="openrouter", ledger_path=ledger,
                    loop_class="lower-order",
                    seat_mode="named", auto_approve=True,
                    max_tokens=6000,
                    transport=lambda m, p: {
                        "id": "x", "model": "openai/gpt-5.5",
                        "choices": [{"message": {"content": "ok"}}],
                        "usage": {"prompt_tokens": 5,
                                  "completion_tokens": 5}})
        self.assertEqual(t["status"], "approved")


if __name__ == "__main__":
    unittest.main()
