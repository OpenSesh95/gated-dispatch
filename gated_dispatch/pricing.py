"""Published list prices used to compute ticket costs (STD-0).

Prices are USD per 1M tokens (input / output). Every entry carries its
source. A (provider, model) pair with no entry raises KeyError on
purpose: an unmetered dispatch must stop the run rather than guess —
the C-004 commission measured a ±50% error band on estimated pricing,
which is why tickets are computed from the API response's actual usage
fields multiplied by these published rates, never from estimates of
the token counts themselves.

Rate notes:
- Anthropic, as published Nov 2026: Opus 5.5 $4/$20, Sonnet 5.5
  $2/$10, Haiku 5.5 $0.10/$0.50 for prompts up to 100K tokens (above
  100K: $0.50/$2.50 — the step is not modelled here; dispatches over
  100K input tokens on Haiku must be priced by hand until it is),
  Fable 5.2 $8/$40.
- Google Gemini paid tier: Argon $2/$10 through 2026-11-30, then
  $4/$20 from 2026-12-01; 3.8 Flash $0.75/$3.75 through 2026-12-31,
  then $1.50/$7.50 from 2027-01-01. Entries below are the rates in
  force on 2026-11-11; the dated step-ups must be applied when they
  land. Gemini output prices include thinking tokens.
- xAI: read from the API's own model list on 2026-11-11
  (api.x.ai/v1/models; raw per-token prices divided by 10,000 give
  USD per 1M). Long-context (>200K tokens) rates double; not modelled.
- Open-weight lane: no verified rates yet (regime NEEDS-SOURCE NS-5),
  so the lane is intentionally unpriced — dispatches on it stop.
"""

# (provider, model) -> (input_usd_per_1m, output_usd_per_1m, source)
PRICES = {
    ("anthropic", "claude-opus-5-5"): (4.00, 20.00, "Anthropic published pricing, Nov 2026"),
    ("anthropic", "claude-sonnet-5-5"): (2.00, 10.00, "Anthropic published pricing, Nov 2026"),
    ("anthropic", "claude-haiku-5-5"): (0.10, 0.50, "Anthropic published pricing, Nov 2026 (<=100K prompt)"),
    ("anthropic", "claude-fable-5-2"): (8.00, 40.00, "Anthropic published pricing, Nov 2026"),
    ("google", "gemini-4-argon"): (2.00, 10.00, "Google published pricing, Nov 2026 (through 2026-11-30)"),
    ("google", "gemini-3.8-flash"): (0.75, 3.75, "Google published pricing, Nov 2026 (through 2026-12-31)"),
    ("xai", "grok-4.20-0309-reasoning"): (1.25, 2.50, "api.x.ai/v1/models, 2026-11-11"),
    ("xai", "grok-4.20-0309-non-reasoning"): (1.25, 2.50, "api.x.ai/v1/models, 2026-11-11"),
    ("openai", "gpt-5"): (1.25, 10.00, "OpenAI published pricing, Nov 2026"),
    ("openai", "gpt-5-mini"): (0.25, 2.00, "OpenAI published pricing, Nov 2026"),
}

PRICE_TABLE_VERSION = "2026-11-11.1"


def price_info(provider: str, model: str):
    """Return (input, output, source) for a lane model, or raise KeyError."""
    key = (provider, model)
    if key not in PRICES:
        raise KeyError(
            f"no published price for {provider}/{model}; add a sourced entry to pricing.py before dispatching"
        )
    return PRICES[key]


def estimate_cost_usd(provider: str, model: str, tokens_in: int, tokens_out: int) -> float:
    """Cost of a dispatch from ACTUAL usage counts at published rates."""
    price_in, price_out, _ = price_info(provider, model)
    return (tokens_in * price_in + tokens_out * price_out) / 1_000_000
