"""List-price table used for cost metering.

Prices are USD per 1M tokens (input / output), as published by each
provider in November 2026. They are estimates for ledger purposes:
verify against the provider's current pricing page before budgeting.
An unlisted model raises KeyError on purpose — an unmetered dispatch
is worse than a stopped one.
"""

PRICES_USD_PER_1M = {
    # model id: (input, output)
    "claude-sonnet-4-5": (3.00, 15.00),
    "claude-haiku-4-5": (1.00, 5.00),
    "gpt-5": (1.25, 10.00),
    "gpt-5-mini": (0.25, 2.00),
    "gemini-2-5-flash": (0.30, 2.50),
    "gemini-2-5-pro": (1.25, 10.00),
}


def estimate_cost_usd(model: str, tokens_in: int, tokens_out: int) -> float:
    """Return the estimated USD cost of one dispatch."""
    if model not in PRICES_USD_PER_1M:
        raise KeyError(
            f"no list price for model {model!r}; add it to pricing.py before dispatching"
        )
    price_in, price_out = PRICES_USD_PER_1M[model]
    return (tokens_in * price_in + tokens_out * price_out) / 1_000_000
