"""Per-model output contracts (C-029 Group B, H-B2).

Each registered id declares, beside its price entry: transport
shape · modality shape · billing basis · cap class. Returns
assert against the declaration. Outcomes:

  PASS            the return matches the declared shape.
  FAIL            the return breaks the declaration (a metering
                  basis drift, an empty return on a text seat).
  PASS-WITH-CAUSE the declared shape behaving as declared on
                  out-of-shape input — the transcribe cases are
                  the exhibits: a text prompt to an audio-in
                  seat is out-of-shape input; its rejection is
                  conformance, never a seat failure.
"""

from __future__ import annotations

from . import lanes

# Declared overrides; everything else derives from lane facts.
OVERRIDES: dict[str, dict] = {
    "gemini-3.5-transcribe": {"modality_in": "audio"},
    "grok-4.20-multi-agent-0309": {"transport": "responses"},
}

CAP_CLASSES = ("standard", "long-form", "reasoning")

# Reasoning-channel models: the reasoning stream consumes the
# output cap before content arrives. Measured on the open-weight
# lane 2026-11-12 (lighthouse BURST-001): qwen3:14b's reasoning
# channel ate the 1024-token cap and the content arrived empty —
# the GT-L2 cap class on the bench lane. Engagements firing
# these ids need a larger output cap or explicit
# reasoning-channel handling in the lane's call shape.
REASONING = {"qwen3:14b", "deepseek-r1:14b",
             "grok-4.20-0309-reasoning"}
LONG_FORM = {"claude-opus-5-5", "claude-fable-5-2",
             "gemini-3.1-pro-preview", "gemini-4-argon",
             "gemini-4-carbon"}


def declaration(provider: str, model: str) -> dict:
    if provider == "anthropic":
        transport = "messages"
    elif provider == "google":
        transport = "generate-content"
    elif model in lanes.RESPONSES_MODELS:
        transport = "responses"
    else:
        transport = "chat"
    from .cli import cost_source_for
    cap = lanes.cap_class_of(model)  # single source: lanes
    decl = {
        "transport": transport,
        "modality_in": "text",
        "billing": cost_source_for(provider, model),
        "cap_class": cap,
    }
    decl.update(OVERRIDES.get(model, {}))
    return decl


def assert_contract(provider: str, model: str, *,
                    cost_source: str | None,
                    text: str | None,
                    input_was_text: bool = True) -> str:
    decl = declaration(provider, model)
    if decl["modality_in"] == "audio" and input_was_text:
        return "PASS-WITH-CAUSE"
    if cost_source is not None and cost_source != decl["billing"]:
        return "FAIL"
    if decl["modality_in"] == "text" and text is not None and not text:
        return "FAIL"
    return "PASS"
