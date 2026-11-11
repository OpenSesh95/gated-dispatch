"""Legacy generic provider call (superseded by lanes.py for STD-0).

Provider call: one chat completion over an OpenAI-compatible HTTP API.

Standard library only. The transport is injectable so the full loop can
be tested offline with a stub; production runs use urllib against the
endpoint named by GATED_DISPATCH_BASE_URL with the key in
GATED_DISPATCH_API_KEY. Keys are read from the environment at call
time and never written anywhere.
"""

import json
import os
import urllib.request
from dataclasses import dataclass


@dataclass
class Completion:
    text: str
    tokens_in: int
    tokens_out: int
    model: str


def http_transport(base_url: str, api_key: str, model: str, prompt: str) -> dict:
    """POST one chat completion; return the decoded JSON body."""
    body = json.dumps(
        {
            "model": model,
            "messages": [{"role": "user", "content": prompt}],
        }
    ).encode("utf-8")
    req = urllib.request.Request(
        base_url.rstrip("/") + "/chat/completions",
        data=body,
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {api_key}",
        },
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=120) as resp:
        return json.loads(resp.read().decode("utf-8"))


def dispatch(prompt: str, model: str, transport=None) -> Completion:
    """Run one dispatch and normalize the provider's response."""
    if transport is None:
        base_url = os.environ["GATED_DISPATCH_BASE_URL"]
        api_key = os.environ["GATED_DISPATCH_API_KEY"]
        transport = lambda m, p: http_transport(base_url, api_key, m, p)
    raw = transport(model, prompt)
    usage = raw.get("usage", {})
    return Completion(
        text=raw["choices"][0]["message"]["content"],
        tokens_in=int(usage.get("prompt_tokens", 0)),
        tokens_out=int(usage.get("completion_tokens", 0)),
        model=raw.get("model", model),
    )
