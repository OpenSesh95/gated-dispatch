"""Lane adapters (STD-0): one per provider API shape.

Each adapter builds the provider's request, and parses the response
into a normalized Completion whose token counts come from the API's
own usage fields — never from local estimation (STD-0; the C-004
±50% pricing-error exhibit is why estimates do not count).

Live transports shell out to the operator's connector helpers, which
hold the API keys in secure storage and place them on the request.
Keys never pass through this code, argv, or the environment here.
Tests inject stub transports returning recorded response shapes.
"""

import json
import os
import subprocess
from dataclasses import dataclass, field

CONNECTOR_HELPERS = {
    "anthropic": "~/workspace/custom-connectors/custom.anthropic/bin/anthropic_call.py",
    "google": "~/workspace/custom-connectors/custom.google-gemini/bin/gemini_call.py",
    "xai": "~/workspace/custom-connectors/custom.xai/bin/xai_call.py",
}

# Lane names used by the budget regime's per-lane sub-ceilings.
LANE_OF_PROVIDER = {
    "anthropic": "anthropic",
    "google": "google",
    "xai": "xai",
    "openai": "open",
    "open": "open",
}


@dataclass
class Completion:
    text: str
    tokens_in: int
    tokens_out: int
    model_served: str
    usage: dict = field(default_factory=dict)


def parse_openai(raw: dict) -> Completion:
    usage = raw.get("usage", {})
    return Completion(
        text=raw["choices"][0]["message"]["content"],
        tokens_in=int(usage.get("prompt_tokens", 0)),
        tokens_out=int(usage.get("completion_tokens", 0)),
        model_served=raw.get("model", ""),
        usage=usage,
    )


def parse_anthropic(raw: dict) -> Completion:
    usage = raw.get("usage", {})
    text = "".join(
        block.get("text", "") for block in raw.get("content", []) if block.get("type") == "text"
    )
    return Completion(
        text=text,
        tokens_in=int(usage.get("input_tokens", 0)),
        tokens_out=int(usage.get("output_tokens", 0)),
        model_served=raw.get("model", ""),
        usage=usage,
    )


def parse_gemini(raw: dict) -> Completion:
    usage = raw.get("usageMetadata", {})
    parts = raw["candidates"][0]["content"]["parts"]
    text = "".join(part.get("text", "") for part in parts)
    # Google bills thinking tokens at the output rate; they are output.
    tokens_out = int(usage.get("candidatesTokenCount", 0)) + int(
        usage.get("thoughtsTokenCount", 0)
    )
    return Completion(
        text=text,
        tokens_in=int(usage.get("promptTokenCount", 0)),
        tokens_out=tokens_out,
        model_served=raw.get("modelVersion", ""),
        usage=usage,
    )


PARSERS = {
    "anthropic": parse_anthropic,
    "google": parse_gemini,
    "xai": parse_openai,
    "openai": parse_openai,
    "open": parse_openai,
}


def request_for(provider: str, model: str, prompt: str):
    """Return (path, body) for the provider's connector helper."""
    if provider == "anthropic":
        return "/v1/messages", {
            "model": model,
            "max_tokens": 1024,
            "messages": [{"role": "user", "content": prompt}],
        }
    if provider == "google":
        return f"/v1beta/models/{model}:generateContent", {
            "contents": [{"parts": [{"text": prompt}]}]
        }
    if provider in ("xai", "openai", "open"):
        return "/v1/chat/completions", {
            "model": model,
            "max_tokens": 1024,
            "messages": [{"role": "user", "content": prompt}],
        }
    raise KeyError(f"unknown provider {provider!r}")


def helper_transport(provider: str):
    """Build a live transport that calls the provider via its helper."""
    helper = os.path.expanduser(CONNECTOR_HELPERS[provider])

    def _transport(model: str, prompt: str) -> dict:
        path, body = request_for(provider, model, prompt)
        proc = subprocess.run(
            ["python3", helper, path, json.dumps(body)],
            capture_output=True,
            text=True,
            timeout=600,
        )
        if proc.returncode != 0:
            raise ConnectionError(
                f"{provider} helper failed ({proc.returncode}): {proc.stderr.strip()[:200]}"
            )
        return json.loads(proc.stdout)

    return _transport


def dispatch(prompt: str, provider: str, model: str, transport=None) -> Completion:
    """Run one dispatch on a lane and normalize the response."""
    if transport is None:
        transport = helper_transport(provider)
    raw = transport(model, prompt)
    completion = PARSERS[provider](raw)
    if not completion.model_served:
        completion.model_served = model
    return completion
