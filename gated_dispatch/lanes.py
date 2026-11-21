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
    # xai serves through the custom.grok registration (repointed
    # 2026-11-17, gate v0.4.32): the working key was captured there
    # and its proofs pass, while custom.xai still holds the
    # truncated value that failed all morning (400 at the API,
    # surfaced at the gate as helper-failure ConnectionErrors).
    "xai": "~/workspace/custom-connectors/custom.grok/bin/grok_call.py",
    "local": "~/workspace/custom-connectors/custom.local-ollama/bin/ollama_call.py",
    "gcp": "~/workspace/custom-connectors/custom.gcp-ollama/bin/ollama_call.py",
    "openrouter": "~/workspace/custom-connectors/custom.openrouter/bin/openrouter_call.py",
}

# OpenRouter serve map (wired 2026-11-12): gate id -> the catalog id that
# serves it on the registered (:free) route, verified against the live
# catalog at wiring. Registered rows with NO entry have no :free form in
# the current catalog (free route lapsed or never existed under that
# form); the lane refuses them by name rather than silently spending
# paid rates against a $0 registration.
OPENROUTER_SERVE_MAP = {
    "nemotron-3-ultra": "nvidia/nemotron-3-ultra-550b-a55b:free",
    "gemma-4-26b-a4b-it": "google/gemma-4-26b-a4b-it:free",
    "gemma-4-31b-it": "google/gemma-4-31b-it:free",
    "flint-v1.0": "recursive/flint-v1.0:free",
    "north-mini-code": "cohere/north-mini-code:free",
}

# Lane names used by the budget regime's per-lane sub-ceilings.
LANE_OF_PROVIDER = {
    "anthropic": "anthropic",
    "google": "google",
    "xai": "xai",
    "openai": "open",
    "open": "open",
    "local": "open",
    "gcp": "open",
    "openrouter": "open",
}


@dataclass
class Completion:
    text: str
    tokens_in: int
    tokens_out: int
    model_served: str
    usage: dict = field(default_factory=dict)
    finish_reason: str | None = None


def normalize_finish(raw_value) -> str | None:
    """Provider finish values -> the scored set (H-B3):
    STOP · MAX_TOKENS · OTHER. Absent reads None (unmeasured)."""
    if raw_value is None:
        return None
    v = str(raw_value).lower()
    if v in ("stop", "end_turn", "stop_sequence", "completed"):
        return "STOP"
    if v in ("length", "max_tokens", "max_output_tokens"):
        return "MAX_TOKENS"
    return "OTHER"


def parse_openai(raw: dict) -> Completion:
    usage = raw.get("usage", {})
    return Completion(
        text=raw["choices"][0]["message"]["content"],
        tokens_in=int(usage.get("prompt_tokens", 0)),
        tokens_out=int(usage.get("completion_tokens", 0)),
        model_served=raw.get("model", ""),
        usage=usage,
        finish_reason=normalize_finish(
            raw["choices"][0].get("finish_reason")),
    )


def parse_openrouter(raw: dict) -> Completion:
    """OpenRouter serves registered gate ids under catalog ids
    (OPENROUTER_SERVE_MAP). When the served id is the registered serve
    form, model_served reads as the gate id (so model_match attests
    'served as registered') and the raw catalog form rides in
    usage['served_form'] as evidence. Any other served id stays raw,
    so true drift still reads model_match=false."""
    completion = parse_openai(raw)
    raw_form = completion.model_served
    for gate_id, served_form in OPENROUTER_SERVE_MAP.items():
        if raw_form == served_form:
            completion.model_served = gate_id
            completion.usage = {**completion.usage,
                                "served_form": raw_form}
            break
    return completion


def parse_xai(raw: dict) -> Completion:
    # xAI bills reasoning tokens at the output rate ON TOP of the
    # completion figure its seat reports carry (proof: panel P-017 —
    # 6,389 in / 1,277 completion + 4,047 reasoning priced by xAI's own
    # cost_in_usd_ticks at $0.0212 = prompt + (completion + reasoning),
    # vs $0.0112 for prompt + completion alone; Treasury exhibit
    # TR-20261112-09, correction executed 2026-11-12). OpenAI proper
    # already includes reasoning inside completion_tokens, so this
    # additive rule is xAI-only — do not apply it in parse_openai.
    usage = raw.get("usage", {})
    if "cost_in_usd_ticks" not in usage and raw.get("cost_in_usd_ticks") is not None:
        usage = {**usage, "cost_in_usd_ticks": raw["cost_in_usd_ticks"]}
    details = usage.get("completion_tokens_details", {}) or {}
    tokens_out = int(usage.get("completion_tokens", 0)) + int(
        details.get("reasoning_tokens", 0)
    )
    return Completion(
        text=raw["choices"][0]["message"]["content"],
        tokens_in=int(usage.get("prompt_tokens", 0)),
        tokens_out=tokens_out,
        model_served=raw.get("model", ""),
        usage=usage,
        finish_reason=normalize_finish(
            raw["choices"][0].get("finish_reason")),
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
        finish_reason=normalize_finish(raw.get("stop_reason")),
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
        finish_reason=normalize_finish(
            raw["candidates"][0].get("finishReason")),
    )


# Ids that refuse chat completions and serve on the Responses API
# (provider's own error, 2026-11-12: "Multi Agent requests are not
# allowed on chat completions", HTTP 400). Id-only routing: every
# other xAI id stays on chat completions.
RESPONSES_MODELS = {"grok-4.20-multi-agent-0309"}


def parse_xai_responses(raw: dict) -> Completion:
    # Responses shape: text rides output[] message items; usage
    # carries input_tokens / output_tokens and the provider's own
    # cost_in_usd_ticks. On this shape output_tokens ALREADY
    # includes reasoning tokens (verified 2026-11-12 by ticks
    # reconciliation: uncached input at list + cached input at the
    # $0.20/1M cached rate + output_tokens at list == the ticks
    # figure exactly; adding reasoning again breaks the equality).
    # Do NOT apply parse_xai's additive reasoning rule here.
    usage = raw.get("usage", {})
    if "cost_in_usd_ticks" not in usage and raw.get("cost_in_usd_ticks") is not None:
        usage = {**usage, "cost_in_usd_ticks": raw["cost_in_usd_ticks"]}
    texts: list[str] = []
    for item in raw.get("output", []):
        if item.get("type") == "message":
            for part in item.get("content", []):
                if part.get("type") == "output_text":
                    texts.append(part.get("text", ""))
    incomplete = (raw.get("incomplete_details") or {}).get("reason")
    return Completion(
        text="".join(texts),
        tokens_in=int(usage.get("input_tokens", 0)),
        tokens_out=int(usage.get("output_tokens", 0)),
        model_served=raw.get("model", ""),
        usage=usage,
        finish_reason=normalize_finish(incomplete or raw.get("status")),
    )


PARSERS = {
    "anthropic": parse_anthropic,
    "google": parse_gemini,
    "xai": parse_xai,
    "openai": parse_openai,
    "open": parse_openai,
    "local": parse_openai,
    "gcp": parse_openai,
    "openrouter": parse_openrouter,
}


# Output-cap policy by contract cap class (the lane call-shape
# handling the defect register names): reasoning and long-form
# seats spend output budget before content arrives — measured
# live on the frontier lane in warm-up cycle W-1, where Sonnet
# and Opus legs returned empty at the flat 1024 cap with
# finish_reason MAX_TOKENS. The flat cap stands for standard.
CAP_BY_CLASS = {"standard": 1024, "long-form": 4096, "reasoning": 4096}
REASONING_MODELS = {"qwen3:14b", "deepseek-r1:14b",
                    "grok-4.20-0309-reasoning",
                    # Reasoning-first frontier seats (v0.4.46): at the
                    # standard 1024 cap their reasoning spend starved
                    # the content to empty — the council bench's four
                    # GPT no-shows (2026-11-20) are the evidence.
                    "openai/gpt-5.5", "openai/o3"}
LONG_FORM_MODELS = {"claude-opus-5-5", "claude-fable-5-2",
                    "claude-sonnet-5-5", "gemini-3.1-pro-preview",
                    "gemini-4-argon", "gemini-4-carbon",
                    "openai/gpt-5.3-codex"}


def cap_class_of(model: str) -> str:
    if model in REASONING_MODELS:
        return "reasoning"
    if model in LONG_FORM_MODELS:
        return "long-form"
    return "standard"


def cap_for(model: str) -> int:
    return CAP_BY_CLASS[cap_class_of(model)]


def request_for(provider: str, model: str, prompt: str, max_tokens=None):
    """Return (path, body) for the provider's connector helper."""
    cap = max_tokens or cap_for(model)
    if provider == "anthropic":
        return "/v1/messages", {
            "model": model,
            "max_tokens": cap,
            "messages": [{"role": "user", "content": prompt}],
        }
    if provider == "google":
        return f"/v1beta/models/{model}:generateContent", {
            "contents": [{"parts": [{"text": prompt}]}]
        }
    if provider == "openrouter":
        # Catalog-form ids (C-038 gauntlet rows) serve as themselves.
        served = model if "/" in model else OPENROUTER_SERVE_MAP.get(model)
        if served is None:
            raise KeyError(
                f"registered-not-served: no :free form for {model!r} in the "
                "current OpenRouter catalog (see docs/free-weights-registry.md)")
        return "/api/v1/chat/completions", {
            "model": served,
            "max_tokens": cap,
            "messages": [{"role": "user", "content": prompt}],
        }
    if provider in ("xai", "openai", "open", "local", "gcp"):
        if provider == "xai" and model in RESPONSES_MODELS:
            return "/v1/responses", {
                "model": model,
                "input": prompt,
                "max_output_tokens": cap,
            }
        return "/v1/chat/completions", {
            "model": model,
            "max_tokens": cap,
            "messages": [{"role": "user", "content": prompt}],
        }
    raise KeyError(f"unknown provider {provider!r}")


def helper_transport(provider: str, max_tokens=None):
    """Build a live transport that calls the provider via its helper.
    max_tokens (v0.4.46) is the caller's explicit output budget; None
    keeps the model's cap-class default from CAP_BY_CLASS."""
    helper = os.path.expanduser(CONNECTOR_HELPERS[provider])

    def _transport(model: str, prompt: str) -> dict:
        path, body = request_for(provider, model, prompt, max_tokens)
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


# Providers whose lane starts cold (a local / self-hosted model
# server that loads the model on first call). C-026 defect (ii).
COLD_START_PROVIDERS = {"local", "gcp"}


def warm(provider: str, model: str, transport=None) -> bool:
    """Start a cold lane BEFORE the acquire clock runs (C-026
    start-then-acquire). One minimal call loads the model on the
    lane's own time; the slot wait that follows then measures true
    contention, not boot. Never raises: a failed warm falls through
    to the normal attempt path, whose errors surface as usual."""
    if provider not in COLD_START_PROVIDERS:
        return False
    try:
        if transport is None:
            transport = helper_transport(provider)
        transport(model, "warm")
        return True
    except Exception:
        return False


def dispatch(prompt: str, provider: str, model: str, transport=None,
             max_tokens=None) -> Completion:
    """Run one dispatch on a lane and normalize the response.
    max_tokens threads to the helper transport only — a caller-supplied
    stub transport keeps the (model, prompt) test seam unchanged."""
    if transport is None:
        transport = helper_transport(provider, max_tokens)
    raw = transport(model, prompt)
    # A provider failure is a LANE failure, not a parse error:
    # normalize every failure shape to ConnectionError so the
    # throttle layer retries, backs off, and feeds the model's
    # error budget uniformly. Shapes seen live: a top-level "error"
    # body, and the Gemini helper's {"http_status", "error_body"}
    # wrapper (error_body is a JSON string) on HTTP 503.
    if isinstance(raw, dict) and int(raw.get("http_status", 0) or 0) >= 400:
        body = raw.get("error_body") or ""
        detail = body
        try:
            parsed = json.loads(body) if isinstance(body, str) else body
            err = (parsed or {}).get("error", {}) if isinstance(parsed, dict) else {}
            detail = err.get("message") or err.get("status") or body
        except (ValueError, AttributeError):
            pass
        raise ConnectionError(
            f"{provider} HTTP {raw['http_status']}: {str(detail)[:200]}"
        )
    if isinstance(raw, dict) and raw.get("error"):
        # Truthiness matters: a Responses-API success body carries
        # "error": null — the key alone is not a failure.
        err = raw["error"] or {}
        if isinstance(err, dict):
            detail = err.get("message") or err.get("status") or str(err)
            code = err.get("code") or err.get("status") or ""
        else:
            detail, code = str(err), ""
        raise ConnectionError(f"{provider} error {code}: {str(detail)[:200]}")
    if provider == "xai" and model in RESPONSES_MODELS:
        completion = parse_xai_responses(raw)
    else:
        completion = PARSERS[provider](raw)
    if not completion.model_served:
        completion.model_served = model
    return completion
