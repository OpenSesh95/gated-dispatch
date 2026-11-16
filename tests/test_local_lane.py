"""Local lane tests (Track A, 2026-11-11): Ollama on the owner's hardware.

The lane is priced at $0.00 on purpose — priced, not unpriced, so its
dispatches run AND ticket, with token counts from the API usage fields.
"""

import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from gated_dispatch.lanes import (LANE_OF_PROVIDER, dispatch, request_for)
from gated_dispatch.pricing import estimate_cost_usd, price_info

LOCAL_MODELS = ("qwen3:14b", "deepseek-r1:14b", "llama3.1:8b")


class TestLocalPricing(unittest.TestCase):
    def test_local_models_priced_at_zero(self):
        for model in LOCAL_MODELS:
            price_in, price_out, source = price_info("local", model)
            self.assertEqual((price_in, price_out), (0.00, 0.00))
            self.assertIn("Local Ollama", source)

    def test_cost_is_zero_with_real_token_counts(self):
        self.assertEqual(
            estimate_cost_usd("local", "qwen3:14b", 12_345, 67_890), 0.0)

    def test_local_draws_the_open_lane(self):
        self.assertEqual(LANE_OF_PROVIDER["local"], "open")


class TestLocalDispatch(unittest.TestCase):
    def test_request_shape_is_openai_compatible(self):
        path, body = request_for("local", "llama3.1:8b", "hello")
        self.assertEqual(path, "/v1/chat/completions")
        self.assertEqual(body["model"], "llama3.1:8b")

    def test_dispatch_parses_usage_from_response(self):
        def stub(model, prompt):
            return {
                "model": model,
                "choices": [{"message": {"content": "lane live"}}],
                "usage": {"prompt_tokens": 19, "completion_tokens": 5},
            }

        completion = dispatch("Reply with exactly: lane live",
                              "local", "llama3.1:8b", transport=stub)
        self.assertEqual(completion.text, "lane live")
        self.assertEqual(completion.tokens_in, 19)
        self.assertEqual(completion.tokens_out, 5)
        self.assertEqual(completion.model_served, "llama3.1:8b")


if __name__ == "__main__":
    unittest.main()
