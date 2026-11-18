"""Throttle table v1 — intelligent throttling at the gate.

Per-lane concurrency + backoff, a concrete-model allowlist with
per-model error budgets, and class-dependent failure behavior:

- COMMODITY loop classes (junior panels, sweeps, scans, mechanical
  runs): on an error-budget breach the loop DEGRADES to the next model
  in its chain automatically instead of stalling (the PD-2 lesson,
  mechanized — a dead Gemini lane must not freeze commodity work).
- DELIBERATIVE loop classes (panels, commissions, Council seats):
  the interim fail-closed rule stands — a breached or failed lane
  STOPS the dispatch; substitution needs an explicit per-instance
  decision. The table encodes both behaviors by class.

Binding constraint at build: the Gemini free-tier quota (the tier
is paid since 2026-11-12; the serial posture stands until a quota
re-check raises it). The google lane runs
at concurrency 1 with a minimum call interval; commodity load spreads
across Gemini Flash classes, Grok fast tiers, and Haiku juniors via
the degrade chains.

Aliases are banned: any model id containing "latest" is refused
(an alias is an unpinned model — its price and behavior can change
under a ticket). Retired models are refused by name.

State (per-model error timestamps, cooldowns, in-flight counts) lives
in one JSON file beside the ledger; every mutation is a locked
read-modify-write so concurrent CLI processes share one truth.
Standard library only.
"""

import json
import os
import time
from dataclasses import dataclass, field

# ---------------------------------------------------------------- table

@dataclass(frozen=True)
class ModelRule:
    provider: str
    concurrency: int = 2
    min_interval_s: float = 0.0
    backoff_base_s: float = 2.0
    backoff_factor: float = 2.0
    backoff_max_s: float = 60.0
    max_retries: int = 2
    error_budget: int = 3          # errors inside the window…
    error_window_s: float = 600.0  # …(rolling) that breach the budget
    cooldown_s: float = 900.0      # budget breached → model rests


MODELS: dict[str, ModelRule] = {
    # Google — serial posture from the free-tier era, retained: serial,
    # spaced calls; a 503 earns backoff, repeats breach the budget.
    "gemini-3.8-flash": ModelRule("google", concurrency=1, min_interval_s=4.0,
                                  backoff_base_s=5.0, max_retries=3,
                                  error_budget=3, cooldown_s=1800.0),
    "gemini-4-argon": ModelRule("google", concurrency=1, min_interval_s=4.0,
                                backoff_base_s=5.0, max_retries=2,
                                error_budget=3, cooldown_s=1800.0),
    # Added 2026-11-12 (P-022 unblock): the panel seats' concrete ids.
    "gemini-3.5-flash": ModelRule("google", concurrency=1, min_interval_s=4.0,
                                  backoff_base_s=5.0, max_retries=3,
                                  error_budget=3, cooldown_s=1800.0),
    "gemini-3.6-flash": ModelRule("google", concurrency=1, min_interval_s=4.0,
                                  backoff_base_s=5.0, max_retries=3,
                                  error_budget=3, cooldown_s=1800.0),
    # gemini-3.7-flash: NO rule — QUARANTINE (C-023 R-2, drift alias).
    "gemini-3.1-pro-preview": ModelRule("google", concurrency=1, min_interval_s=4.0,
                                        backoff_base_s=5.0, max_retries=2,
                                        error_budget=3, cooldown_s=1800.0),
    "gemini-3.5-flash-lite": ModelRule("google", concurrency=1, min_interval_s=4.0,
                                       backoff_base_s=5.0, max_retries=3,
                                       error_budget=3, cooldown_s=1800.0),
    "gemini-3.1-flash-lite": ModelRule("google", concurrency=1, min_interval_s=4.0,
                                       backoff_base_s=5.0, max_retries=3,
                                       error_budget=3, cooldown_s=1800.0),
    "gemini-3.1-flash-lite-preview": ModelRule("google", concurrency=1, min_interval_s=4.0,
                                               backoff_base_s=5.0, max_retries=3,
                                               error_budget=3, cooldown_s=1800.0),
    # C-023 registration batch (2026-11-12), fixed order.
    "gemini-4-carbon": ModelRule("google", concurrency=1, min_interval_s=4.0,
                                 backoff_base_s=5.0, max_retries=2,
                                 error_budget=3, cooldown_s=1800.0),
    "gemini-4-hydrogen": ModelRule("google", concurrency=1, min_interval_s=4.0,
                                   backoff_base_s=5.0, max_retries=3,
                                   error_budget=3, cooldown_s=1800.0),
    "gemini-3.1-pro-preview-customtools": ModelRule("google", concurrency=1, min_interval_s=4.0,
                                                    backoff_base_s=5.0, max_retries=2,
                                                    error_budget=3, cooldown_s=1800.0),
    "gemini-3.5-transcribe": ModelRule("google", concurrency=1, min_interval_s=4.0,
                                       backoff_base_s=5.0, max_retries=3,
                                       error_budget=3, cooldown_s=1800.0),
    "gemma-4-26b-a4b-it": ModelRule("google", concurrency=1, min_interval_s=4.0,
                                    backoff_base_s=5.0, max_retries=3,
                                    error_budget=3, cooldown_s=1800.0),
    "gemma-4-31b-it": ModelRule("google", concurrency=1, min_interval_s=4.0,
                                backoff_base_s=5.0, max_retries=3,
                                error_budget=3, cooldown_s=1800.0),
    "gemini-robotics-er-2-preview": ModelRule("google", concurrency=1, min_interval_s=4.0,
                                              backoff_base_s=5.0, max_retries=3,
                                              error_budget=3, cooldown_s=1800.0),
    # OpenRouter wired rows (2026-11-12): ONLY the rows whose :free serve
    # form is verified in the live catalog (lanes.OPENROUTER_SERVE_MAP).
    # A rule makes a row fireable under discipline for named-mode proof;
    # it is NOT a seating — these ids enter no chain, and M-class
    # enforcement (cli) refuses them to sensitive loop classes.
    "nemotron-3-ultra": ModelRule("openrouter", concurrency=1, min_interval_s=1.0),
    "gemma-4-26b-a4b-it": ModelRule("openrouter", concurrency=1, min_interval_s=1.0),
    "gemma-4-31b-it": ModelRule("openrouter", concurrency=1, min_interval_s=1.0),
    "flint-v1.0": ModelRule("openrouter", concurrency=1, min_interval_s=1.0),
    "north-mini-code": ModelRule("openrouter", concurrency=1, min_interval_s=1.0),


# C-038 GAUNTLET generated rules (catalog ids; named-mode measurement only).
    'google/gemini-4-hydrogen': ModelRule("openrouter", concurrency=1, min_interval_s=0.5, max_retries=1),
    'google/gemini-4-hydrogen:batch': ModelRule("openrouter", concurrency=1, min_interval_s=0.5, max_retries=1),
    'baidu/ernie-5.5-flash-preview:free': ModelRule("openrouter", concurrency=1, min_interval_s=0.5, max_retries=1),
    'baidu/ernie-light-dt-1.0-intl': ModelRule("openrouter", concurrency=1, min_interval_s=0.5, max_retries=1),
    'google/gemini-4-carbon': ModelRule("openrouter", concurrency=1, min_interval_s=0.5, max_retries=1),
    'google/gemini-4-carbon:batch': ModelRule("openrouter", concurrency=1, min_interval_s=0.5, max_retries=1),
    'nex-agi/nex-n2.6': ModelRule("openrouter", concurrency=1, min_interval_s=0.5, max_retries=1),
    'thinkingmachines/inkling-2-small': ModelRule("openrouter", concurrency=1, min_interval_s=0.5, max_retries=1),
    'thinkingmachines/inkling-2-small:free': ModelRule("openrouter", concurrency=1, min_interval_s=0.5, max_retries=1),
    'anthropic/claude-fable-5.2': ModelRule("openrouter", concurrency=1, min_interval_s=0.5, max_retries=1),
    'anthropic/claude-fable-5.2:batch': ModelRule("openrouter", concurrency=1, min_interval_s=0.5, max_retries=1),
    'meta/muse-ember': ModelRule("openrouter", concurrency=1, min_interval_s=0.5, max_retries=1),
    'liquid/lfm-3-1.7b': ModelRule("openrouter", concurrency=1, min_interval_s=0.5, max_retries=1),
    'liquid/lfm-3-1.7b:free': ModelRule("openrouter", concurrency=1, min_interval_s=0.5, max_retries=1),
    'google/gemini-omni-1.2-flash': ModelRule("openrouter", concurrency=1, min_interval_s=0.5, max_retries=1),
    'kt/midm-k-3.0-pro': ModelRule("openrouter", concurrency=1, min_interval_s=0.5, max_retries=1),
    'google/gemini-omni-1.1-flash': ModelRule("openrouter", concurrency=1, min_interval_s=0.5, max_retries=1),
    'ricursiveai/ripple-65b-preview': ModelRule("openrouter", concurrency=1, min_interval_s=0.5, max_retries=1),
    'tencent/hy4': ModelRule("openrouter", concurrency=1, min_interval_s=0.5, max_retries=1),
    'motif-technologies/motif-3': ModelRule("openrouter", concurrency=1, min_interval_s=0.5, max_retries=1),
    'z-ai/glm-5.3-flashx-legal': ModelRule("openrouter", concurrency=1, min_interval_s=0.5, max_retries=1),
    'particle-ai/particle-1': ModelRule("openrouter", concurrency=1, min_interval_s=0.5, max_retries=1),
    'particle-ai/particle-1:free': ModelRule("openrouter", concurrency=1, min_interval_s=0.5, max_retries=1),
    'openai/gpt-6.1-terra-pro': ModelRule("openrouter", concurrency=1, min_interval_s=0.5, max_retries=1),
    'openai/gpt-6.1-terra-pro:batch': ModelRule("openrouter", concurrency=1, min_interval_s=0.5, max_retries=1),
    'openai/gpt-6.1-terra': ModelRule("openrouter", concurrency=1, min_interval_s=0.5, max_retries=1),
    'openai/gpt-6.1-terra:batch': ModelRule("openrouter", concurrency=1, min_interval_s=0.5, max_retries=1),
    'moonshotai/kimi-k3.1-pro': ModelRule("openrouter", concurrency=1, min_interval_s=0.5, max_retries=1),
    'moonshotai/kimi-k3.1-pro:batch': ModelRule("openrouter", concurrency=1, min_interval_s=0.5, max_retries=1),
    'recursive/flint-v1.0:free': ModelRule("openrouter", concurrency=1, min_interval_s=0.5, max_retries=1),
    'minimax/minimax-m3.1-flash': ModelRule("openrouter", concurrency=1, min_interval_s=0.5, max_retries=1),
    'deepseek/deepseek-v4.1-flash-1017': ModelRule("openrouter", concurrency=1, min_interval_s=0.5, max_retries=1),
    'deepseek/deepseek-v4.1-flash-1017:batch': ModelRule("openrouter", concurrency=1, min_interval_s=0.5, max_retries=1),
    'elorian/glimpse': ModelRule("openrouter", concurrency=1, min_interval_s=0.5, max_retries=1),
    'reflection/beam-1.0-501b-a23b': ModelRule("openrouter", concurrency=1, min_interval_s=0.5, max_retries=1),
    'prism-ml/ternary-bonsai-2-9b': ModelRule("openrouter", concurrency=1, min_interval_s=0.5, max_retries=1),
    'moondream/moondream3-preview': ModelRule("openrouter", concurrency=1, min_interval_s=0.5, max_retries=1),
    'moondream/moondream3.1-9b-a2b': ModelRule("openrouter", concurrency=1, min_interval_s=0.5, max_retries=1),
    'meta/muse-spark-open': ModelRule("openrouter", concurrency=1, min_interval_s=0.5, max_retries=1),
    'nvidia/nemotron-3.5-super-vl': ModelRule("openrouter", concurrency=1, min_interval_s=0.5, max_retries=1),
    'nvidia/nemotron-3.5-super-vl:free': ModelRule("openrouter", concurrency=1, min_interval_s=0.5, max_retries=1),
    'unbiased/pareto-26.10': ModelRule("openrouter", concurrency=1, min_interval_s=0.5, max_retries=1),
    '~unbiased/pareto-latest': ModelRule("openrouter", concurrency=1, min_interval_s=0.5, max_retries=1),
    'unbiased/pareto-26.9': ModelRule("openrouter", concurrency=1, min_interval_s=0.5, max_retries=1),
    'liquid/lfm-2.5-24b-a2b': ModelRule("openrouter", concurrency=1, min_interval_s=0.5, max_retries=1),
    'google/gemini-4-argon': ModelRule("openrouter", concurrency=1, min_interval_s=0.5, max_retries=1),
    'google/gemini-4-argon:batch': ModelRule("openrouter", concurrency=1, min_interval_s=0.5, max_retries=1),
    'scaledown/summarize': ModelRule("openrouter", concurrency=1, min_interval_s=0.5, max_retries=1),
    'scaledown/extract': ModelRule("openrouter", concurrency=1, min_interval_s=0.5, max_retries=1),
    'meta/muse-wonder': ModelRule("openrouter", concurrency=1, min_interval_s=0.5, max_retries=1),
    'stepfun/step-5-preview': ModelRule("openrouter", concurrency=1, min_interval_s=0.5, max_retries=1),
    'anthropic/claude-haiku-5.5': ModelRule("openrouter", concurrency=1, min_interval_s=0.5, max_retries=1),
    'anthropic/claude-haiku-5.5:batch': ModelRule("openrouter", concurrency=1, min_interval_s=0.5, max_retries=1),
    'google/gemini-nano-banana-2.1': ModelRule("openrouter", concurrency=1, min_interval_s=0.5, max_retries=1),
    'mistralai/mistral-large-4-0': ModelRule("openrouter", concurrency=1, min_interval_s=0.5, max_retries=1),
    'inclusionai/ling-3.1-flash': ModelRule("openrouter", concurrency=1, min_interval_s=0.5, max_retries=1),
    'apodex/apodex-1.1-mini:free': ModelRule("openrouter", concurrency=1, min_interval_s=0.5, max_retries=1),
    'unbiased/pareto-26.10-preview': ModelRule("openrouter", concurrency=1, min_interval_s=0.5, max_retries=1),
    'openai/gpt-6.1-sol-pro': ModelRule("openrouter", concurrency=1, min_interval_s=0.5, max_retries=1),
    'openai/gpt-6.1-sol-pro:batch': ModelRule("openrouter", concurrency=1, min_interval_s=0.5, max_retries=1),
    'openai/gpt-6.1-sol': ModelRule("openrouter", concurrency=1, min_interval_s=0.5, max_retries=1),
    'openai/gpt-6.1-sol:batch': ModelRule("openrouter", concurrency=1, min_interval_s=0.5, max_retries=1),
    'anthropic/claude-sonnet-5.5': ModelRule("openrouter", concurrency=1, min_interval_s=0.5, max_retries=1),
    'anthropic/claude-sonnet-5.5:batch': ModelRule("openrouter", concurrency=1, min_interval_s=0.5, max_retries=1),
    'perceptron/perceptron-mk1.5': ModelRule("openrouter", concurrency=1, min_interval_s=0.5, max_retries=1),
    'fireworks/ember-1': ModelRule("openrouter", concurrency=1, min_interval_s=0.5, max_retries=1),
    'z-ai/glm-5.3-prime': ModelRule("openrouter", concurrency=1, min_interval_s=0.5, max_retries=1),
    'qwen/qwen3.8-max-prime': ModelRule("openrouter", concurrency=1, min_interval_s=0.5, max_retries=1),
    'aion-labs/aion-3.5-mini': ModelRule("openrouter", concurrency=1, min_interval_s=0.5, max_retries=1),
    'aion-labs/aion-3.5': ModelRule("openrouter", concurrency=1, min_interval_s=0.5, max_retries=1),
    'upstage/solar-mini4': ModelRule("openrouter", concurrency=1, min_interval_s=0.5, max_retries=1),
    'cohere/command-a-plus': ModelRule("openrouter", concurrency=1, min_interval_s=0.5, max_retries=1),
    'openai/gpt-6-luna-pro': ModelRule("openrouter", concurrency=1, min_interval_s=0.5, max_retries=1),
    'openai/gpt-6-luna-pro:batch': ModelRule("openrouter", concurrency=1, min_interval_s=0.5, max_retries=1),
    'openai/gpt-6-luna': ModelRule("openrouter", concurrency=1, min_interval_s=0.5, max_retries=1),
    'openai/gpt-6-luna:batch': ModelRule("openrouter", concurrency=1, min_interval_s=0.5, max_retries=1),
    'openai/gpt-6-sol-pro': ModelRule("openrouter", concurrency=1, min_interval_s=0.5, max_retries=1),
    'openai/gpt-6-sol-pro:batch': ModelRule("openrouter", concurrency=1, min_interval_s=0.5, max_retries=1),
    'openai/gpt-6-sol': ModelRule("openrouter", concurrency=1, min_interval_s=0.5, max_retries=1),
    'openai/gpt-6-sol:batch': ModelRule("openrouter", concurrency=1, min_interval_s=0.5, max_retries=1),
    'anthropic/claude-opus-5.5': ModelRule("openrouter", concurrency=1, min_interval_s=0.5, max_retries=1),
    'anthropic/claude-opus-5.5:batch': ModelRule("openrouter", concurrency=1, min_interval_s=0.5, max_retries=1),
    'xiaomi/mimo-v2.6-pro-ultraspeed': ModelRule("openrouter", concurrency=1, min_interval_s=0.5, max_retries=1),
    'xiaomi/mimo-v2.6-flash': ModelRule("openrouter", concurrency=1, min_interval_s=0.5, max_retries=1),
    'xiaomi/mimo-v2.6-pro': ModelRule("openrouter", concurrency=1, min_interval_s=0.5, max_retries=1),
    'x-ai/grok-4.7': ModelRule("openrouter", concurrency=1, min_interval_s=0.5, max_retries=1),
    'x-ai/grok-4.7:batch': ModelRule("openrouter", concurrency=1, min_interval_s=0.5, max_retries=1),
    'qwen/qwen3.8-omni-flash': ModelRule("openrouter", concurrency=1, min_interval_s=0.5, max_retries=1),
    'prism-ml/ternary-bonsai-2-27b': ModelRule("openrouter", concurrency=1, min_interval_s=0.5, max_retries=1),
    'z-ai/glm-5.3-flashx': ModelRule("openrouter", concurrency=1, min_interval_s=0.5, max_retries=1),
    '~deepseek/deepseek-pro-latest': ModelRule("openrouter", concurrency=1, min_interval_s=0.5, max_retries=1),
    '~deepseek/deepseek-flash-latest': ModelRule("openrouter", concurrency=1, min_interval_s=0.5, max_retries=1),
    'inference-net/schematron-v2-turbo': ModelRule("openrouter", concurrency=1, min_interval_s=0.5, max_retries=1),
    'inference-net/schematron-v2-small': ModelRule("openrouter", concurrency=1, min_interval_s=0.5, max_retries=1),
    '~openai/gpt-astra-latest': ModelRule("openrouter", concurrency=1, min_interval_s=0.5, max_retries=1),
    '~openai/gpt-sol-latest': ModelRule("openrouter", concurrency=1, min_interval_s=0.5, max_retries=1),
    '~openai/gpt-terra-latest': ModelRule("openrouter", concurrency=1, min_interval_s=0.5, max_retries=1),
    '~openai/gpt-luna-latest': ModelRule("openrouter", concurrency=1, min_interval_s=0.5, max_retries=1),
    'sakana/fugu-ultra-v2': ModelRule("openrouter", concurrency=1, min_interval_s=0.5, max_retries=1),
    'sakana/fugu-max': ModelRule("openrouter", concurrency=1, min_interval_s=0.5, max_retries=1),
    'inclusionai/ling-3.0-flash-vl': ModelRule("openrouter", concurrency=1, min_interval_s=0.5, max_retries=1),
    'deepseek/deepseek-v4.1-flash': ModelRule("openrouter", concurrency=1, min_interval_s=0.5, max_retries=1),
    'deepseek/deepseek-v4.1-flash:batch': ModelRule("openrouter", concurrency=1, min_interval_s=0.5, max_retries=1),
    'nex-agi/nex-n2.5-mini': ModelRule("openrouter", concurrency=1, min_interval_s=0.5, max_retries=1),
    'nex-agi/nex-n2.5-pro': ModelRule("openrouter", concurrency=1, min_interval_s=0.5, max_retries=1),
    'openai/gpt-6-astra': ModelRule("openrouter", concurrency=1, min_interval_s=0.5, max_retries=1),
    'openai/gpt-6-astra:batch': ModelRule("openrouter", concurrency=1, min_interval_s=0.5, max_retries=1),
    'openai/gpt-6-astra-pro': ModelRule("openrouter", concurrency=1, min_interval_s=0.5, max_retries=1),
    'openai/gpt-6-astra-pro:batch': ModelRule("openrouter", concurrency=1, min_interval_s=0.5, max_retries=1),
    'inclusionai/ling-3.0-flash-sante': ModelRule("openrouter", concurrency=1, min_interval_s=0.5, max_retries=1),
    'qwen/qwen3.8-max-0902': ModelRule("openrouter", concurrency=1, min_interval_s=0.5, max_retries=1),
    'qwen/qwen3.8-max-0902:batch': ModelRule("openrouter", concurrency=1, min_interval_s=0.5, max_retries=1),
    'meta/muse-spark-1.3-contributor': ModelRule("openrouter", concurrency=1, min_interval_s=0.5, max_retries=1),
    'meta/muse-spark-1.3': ModelRule("openrouter", concurrency=1, min_interval_s=0.5, max_retries=1),
    'google/gemini-3.8-flash': ModelRule("openrouter", concurrency=1, min_interval_s=0.5, max_retries=1),
    'google/gemini-3.8-flash:batch': ModelRule("openrouter", concurrency=1, min_interval_s=0.5, max_retries=1),
    'anthropic/claude-fable-5.1': ModelRule("openrouter", concurrency=1, min_interval_s=0.5, max_retries=1),
    'anthropic/claude-fable-5.1:batch': ModelRule("openrouter", concurrency=1, min_interval_s=0.5, max_retries=1),
    'ibm-granite/granite-4.2-8b': ModelRule("openrouter", concurrency=1, min_interval_s=0.5, max_retries=1),
    'tencent/hy4-preview': ModelRule("openrouter", concurrency=1, min_interval_s=0.5, max_retries=1),
    'inclusionai/ling-3.0-flash-fin': ModelRule("openrouter", concurrency=1, min_interval_s=0.5, max_retries=1),
    '~z-ai/glm-flash-latest': ModelRule("openrouter", concurrency=1, min_interval_s=0.5, max_retries=1),
    'qwen/qwen3.8-flash': ModelRule("openrouter", concurrency=1, min_interval_s=0.5, max_retries=1),
    'z-ai/glm-5.3-flash': ModelRule("openrouter", concurrency=1, min_interval_s=0.5, max_retries=1),
    'z-ai/glm-5.3-flash:batch': ModelRule("openrouter", concurrency=1, min_interval_s=0.5, max_retries=1),
    'meta/muse-spark-1.2-contributor': ModelRule("openrouter", concurrency=1, min_interval_s=0.5, max_retries=1),
    'deepseek/deepseek-v4-flash-vision-exp': ModelRule("openrouter", concurrency=1, min_interval_s=0.5, max_retries=1),
    'tencent/hy-mt2-1.8b': ModelRule("openrouter", concurrency=1, min_interval_s=0.5, max_retries=1),
    'tencent/hy-mt2-30b-a3b': ModelRule("openrouter", concurrency=1, min_interval_s=0.5, max_retries=1),
    '~z-ai/glm-latest': ModelRule("openrouter", concurrency=1, min_interval_s=0.5, max_retries=1),
    'tencent/hy-mt2-7b': ModelRule("openrouter", concurrency=1, min_interval_s=0.5, max_retries=1),
    'z-ai/glm-5.3': ModelRule("openrouter", concurrency=1, min_interval_s=0.5, max_retries=1),
    'z-ai/glm-5.3:batch': ModelRule("openrouter", concurrency=1, min_interval_s=0.5, max_retries=1),
    'qwen/qwen3.8-27b': ModelRule("openrouter", concurrency=1, min_interval_s=0.5, max_retries=1),
    'qwen/qwen3.8-27b:batch': ModelRule("openrouter", concurrency=1, min_interval_s=0.5, max_retries=1),
    'dots-studio/dots-3-note-preview:free': ModelRule("openrouter", concurrency=1, min_interval_s=0.5, max_retries=1),
    'google/gemini-3.7-flash': ModelRule("openrouter", concurrency=1, min_interval_s=0.5, max_retries=1),
    'google/gemini-3.7-flash:batch': ModelRule("openrouter", concurrency=1, min_interval_s=0.5, max_retries=1),
    'bytedance-seed/seed-2-1-turbo': ModelRule("openrouter", concurrency=1, min_interval_s=0.5, max_retries=1),
    'qwen/qwen3.8-2.4t-a95b': ModelRule("openrouter", concurrency=1, min_interval_s=0.5, max_retries=1),
    'deepseek/deepseek-v4-pro-0813': ModelRule("openrouter", concurrency=1, min_interval_s=0.5, max_retries=1),
    'x-ai/grok-4.6': ModelRule("openrouter", concurrency=1, min_interval_s=0.5, max_retries=1),
    'x-ai/grok-4.6:batch': ModelRule("openrouter", concurrency=1, min_interval_s=0.5, max_retries=1),
    'liquid/lfm-2.5-2.6b': ModelRule("openrouter", concurrency=1, min_interval_s=0.5, max_retries=1),
    'liquid/lfm-2.5-2.6b:free': ModelRule("openrouter", concurrency=1, min_interval_s=0.5, max_retries=1),
    'nvidia/nemotron-3.5-lightning': ModelRule("openrouter", concurrency=1, min_interval_s=0.5, max_retries=1),
    'nvidia/nemotron-3.5-lightning:free': ModelRule("openrouter", concurrency=1, min_interval_s=0.5, max_retries=1),
    'sakana/sakana-namazu': ModelRule("openrouter", concurrency=1, min_interval_s=0.5, max_retries=1),
    'upstage/solar-pro4': ModelRule("openrouter", concurrency=1, min_interval_s=0.5, max_retries=1),
    'meta/muse-glimmer-30b': ModelRule("openrouter", concurrency=1, min_interval_s=0.5, max_retries=1),
    'meta/muse-glimmer-30b:batch': ModelRule("openrouter", concurrency=1, min_interval_s=0.5, max_retries=1),
    'inclusionai/ling-3.0-tiny': ModelRule("openrouter", concurrency=1, min_interval_s=0.5, max_retries=1),
    'meta/muse-spark-1.2': ModelRule("openrouter", concurrency=1, min_interval_s=0.5, max_retries=1),
    '~deepseek/deepseek-v4-flash-latest': ModelRule("openrouter", concurrency=1, min_interval_s=0.5, max_retries=1),
    'deepseek/deepseek-v4-flash-0731': ModelRule("openrouter", concurrency=1, min_interval_s=0.5, max_retries=1),
    'deepseek/deepseek-v4-flash-0731:batch': ModelRule("openrouter", concurrency=1, min_interval_s=0.5, max_retries=1),
    'thinkingmachines/inkling-small': ModelRule("openrouter", concurrency=1, min_interval_s=0.5, max_retries=1),
    'thinkingmachines/inkling-small:batch': ModelRule("openrouter", concurrency=1, min_interval_s=0.5, max_retries=1),
    'qwen/qwen3.7-flash': ModelRule("openrouter", concurrency=1, min_interval_s=0.5, max_retries=1),
    'anthropic/claude-opus-5': ModelRule("openrouter", concurrency=1, min_interval_s=0.5, max_retries=1),
    'anthropic/claude-opus-5:batch': ModelRule("openrouter", concurrency=1, min_interval_s=0.5, max_retries=1),
    'inclusionai/ling-3.0-flash': ModelRule("openrouter", concurrency=1, min_interval_s=0.5, max_retries=1),
    'google/gemini-3.6-flash': ModelRule("openrouter", concurrency=1, min_interval_s=0.5, max_retries=1),
    'google/gemini-3.6-flash:batch': ModelRule("openrouter", concurrency=1, min_interval_s=0.5, max_retries=1),
    'google/gemini-3.5-flash-lite': ModelRule("openrouter", concurrency=1, min_interval_s=0.5, max_retries=1),
    'google/gemini-3.5-flash-lite:batch': ModelRule("openrouter", concurrency=1, min_interval_s=0.5, max_retries=1),
    'meituan/longcat-2.0': ModelRule("openrouter", concurrency=1, min_interval_s=0.5, max_retries=1),
    'thinkingmachines/inkling': ModelRule("openrouter", concurrency=1, min_interval_s=0.5, max_retries=1),
    'moonshotai/kimi-k3': ModelRule("openrouter", concurrency=1, min_interval_s=0.5, max_retries=1),
    'moonshotai/kimi-k3:batch': ModelRule("openrouter", concurrency=1, min_interval_s=0.5, max_retries=1),
    'meta/muse-spark-1.1': ModelRule("openrouter", concurrency=1, min_interval_s=0.5, max_retries=1),
    'openai/gpt-5.6-luna-pro': ModelRule("openrouter", concurrency=1, min_interval_s=0.5, max_retries=1),
    'openai/gpt-5.6-luna-pro:batch': ModelRule("openrouter", concurrency=1, min_interval_s=0.5, max_retries=1),
    'openai/gpt-5.6-luna': ModelRule("openrouter", concurrency=1, min_interval_s=0.5, max_retries=1),
    'openai/gpt-5.6-luna:batch': ModelRule("openrouter", concurrency=1, min_interval_s=0.5, max_retries=1),
    'openai/gpt-5.6-terra-pro': ModelRule("openrouter", concurrency=1, min_interval_s=0.5, max_retries=1),
    'openai/gpt-5.6-terra-pro:batch': ModelRule("openrouter", concurrency=1, min_interval_s=0.5, max_retries=1),
    'openai/gpt-5.6-terra': ModelRule("openrouter", concurrency=1, min_interval_s=0.5, max_retries=1),
    'openai/gpt-5.6-terra:batch': ModelRule("openrouter", concurrency=1, min_interval_s=0.5, max_retries=1),
    'openai/gpt-5.6-sol-pro': ModelRule("openrouter", concurrency=1, min_interval_s=0.5, max_retries=1),
    'openai/gpt-5.6-sol-pro:batch': ModelRule("openrouter", concurrency=1, min_interval_s=0.5, max_retries=1),
    'openai/gpt-5.6-sol': ModelRule("openrouter", concurrency=1, min_interval_s=0.5, max_retries=1),
    'openai/gpt-5.6-sol:batch': ModelRule("openrouter", concurrency=1, min_interval_s=0.5, max_retries=1),
    'x-ai/grok-4.5': ModelRule("openrouter", concurrency=1, min_interval_s=0.5, max_retries=1),
    '~x-ai/grok-latest': ModelRule("openrouter", concurrency=1, min_interval_s=0.5, max_retries=1),
    'aion-labs/aion-3.0-mini': ModelRule("openrouter", concurrency=1, min_interval_s=0.5, max_retries=1),
    'aion-labs/aion-3.0': ModelRule("openrouter", concurrency=1, min_interval_s=0.5, max_retries=1),
    'tencent/hy3': ModelRule("openrouter", concurrency=1, min_interval_s=0.5, max_retries=1),
    'anthropic/claude-sonnet-5': ModelRule("openrouter", concurrency=1, min_interval_s=0.5, max_retries=1),
    'anthropic/claude-sonnet-5:batch': ModelRule("openrouter", concurrency=1, min_interval_s=0.5, max_retries=1),
    'google/gemini-3.1-flash-lite-image': ModelRule("openrouter", concurrency=1, min_interval_s=0.5, max_retries=1),
    'sakana/fugu-ultra': ModelRule("openrouter", concurrency=1, min_interval_s=0.5, max_retries=1),
    'google/gemini-3.1-flash-image': ModelRule("openrouter", concurrency=1, min_interval_s=0.5, max_retries=1),
    'google/gemini-3-pro-image': ModelRule("openrouter", concurrency=1, min_interval_s=0.5, max_retries=1),
    'cohere/north-mini-code:free': ModelRule("openrouter", concurrency=1, min_interval_s=0.5, max_retries=1),
    'z-ai/glm-5.2': ModelRule("openrouter", concurrency=1, min_interval_s=0.5, max_retries=1),
    'z-ai/glm-5.2:batch': ModelRule("openrouter", concurrency=1, min_interval_s=0.5, max_retries=1),
    'moonshotai/kimi-k2.7-code': ModelRule("openrouter", concurrency=1, min_interval_s=0.5, max_retries=1),
    '~anthropic/claude-fable-latest': ModelRule("openrouter", concurrency=1, min_interval_s=0.5, max_retries=1),
    'anthropic/claude-fable-5': ModelRule("openrouter", concurrency=1, min_interval_s=0.5, max_retries=1),
    'anthropic/claude-fable-5:batch': ModelRule("openrouter", concurrency=1, min_interval_s=0.5, max_retries=1),
    'nvidia/nemotron-3.5-content-safety': ModelRule("openrouter", concurrency=1, min_interval_s=0.5, max_retries=1),
    'nvidia/nemotron-3-ultra-550b-a55b': ModelRule("openrouter", concurrency=1, min_interval_s=0.5, max_retries=1),
    'nvidia/nemotron-3-ultra-550b-a55b:free': ModelRule("openrouter", concurrency=1, min_interval_s=0.5, max_retries=1),
    'qwen/qwen3.7-plus': ModelRule("openrouter", concurrency=1, min_interval_s=0.5, max_retries=1),
    'qwen/qwen3.7-plus:batch': ModelRule("openrouter", concurrency=1, min_interval_s=0.5, max_retries=1),
    'minimax/minimax-m3': ModelRule("openrouter", concurrency=1, min_interval_s=0.5, max_retries=1),
    'minimax/minimax-m3:batch': ModelRule("openrouter", concurrency=1, min_interval_s=0.5, max_retries=1),
    'stepfun/step-3.7-flash': ModelRule("openrouter", concurrency=1, min_interval_s=0.5, max_retries=1),
    'anthropic/claude-opus-4.8': ModelRule("openrouter", concurrency=1, min_interval_s=0.5, max_retries=1),
    'anthropic/claude-opus-4.8:batch': ModelRule("openrouter", concurrency=1, min_interval_s=0.5, max_retries=1),
    'qwen/qwen3.7-max': ModelRule("openrouter", concurrency=1, min_interval_s=0.5, max_retries=1),
    'x-ai/grok-build-0.1': ModelRule("openrouter", concurrency=1, min_interval_s=0.5, max_retries=1),
    'google/gemini-3.5-flash': ModelRule("openrouter", concurrency=1, min_interval_s=0.5, max_retries=1),
    'google/gemini-3.5-flash:batch': ModelRule("openrouter", concurrency=1, min_interval_s=0.5, max_retries=1),
    'perceptron/perceptron-mk1': ModelRule("openrouter", concurrency=1, min_interval_s=0.5, max_retries=1),
    'google/gemini-3.1-flash-lite': ModelRule("openrouter", concurrency=1, min_interval_s=0.5, max_retries=1),
    'google/gemini-3.1-flash-lite:batch': ModelRule("openrouter", concurrency=1, min_interval_s=0.5, max_retries=1),
    'openai/gpt-chat-latest': ModelRule("openrouter", concurrency=1, min_interval_s=0.5, max_retries=1),
    'x-ai/grok-4.3': ModelRule("openrouter", concurrency=1, min_interval_s=0.5, max_retries=1),
    'x-ai/grok-4.3:batch': ModelRule("openrouter", concurrency=1, min_interval_s=0.5, max_retries=1),
    'mistralai/mistral-medium-3-5': ModelRule("openrouter", concurrency=1, min_interval_s=0.5, max_retries=1),
    'mistralai/mistral-medium-3-5:batch': ModelRule("openrouter", concurrency=1, min_interval_s=0.5, max_retries=1),
    'nvidia/nemotron-3-nano-omni-30b-a3b-reasoning:free': ModelRule("openrouter", concurrency=1, min_interval_s=0.5, max_retries=1),
    '~anthropic/claude-haiku-latest': ModelRule("openrouter", concurrency=1, min_interval_s=0.5, max_retries=1),
    '~openai/gpt-mini-latest': ModelRule("openrouter", concurrency=1, min_interval_s=0.5, max_retries=1),
    '~google/gemini-pro-latest': ModelRule("openrouter", concurrency=1, min_interval_s=0.5, max_retries=1),
    '~moonshotai/kimi-latest': ModelRule("openrouter", concurrency=1, min_interval_s=0.5, max_retries=1),
    '~google/gemini-flash-latest': ModelRule("openrouter", concurrency=1, min_interval_s=0.5, max_retries=1),
    '~anthropic/claude-sonnet-latest': ModelRule("openrouter", concurrency=1, min_interval_s=0.5, max_retries=1),
    'qwen/qwen3.5-plus-20260420': ModelRule("openrouter", concurrency=1, min_interval_s=0.5, max_retries=1),
    'qwen/qwen3.6-flash': ModelRule("openrouter", concurrency=1, min_interval_s=0.5, max_retries=1),
    'qwen/qwen3.6-35b-a3b': ModelRule("openrouter", concurrency=1, min_interval_s=0.5, max_retries=1),
    'qwen/qwen3.6-27b': ModelRule("openrouter", concurrency=1, min_interval_s=0.5, max_retries=1),
    'openai/gpt-5.5-pro': ModelRule("openrouter", concurrency=1, min_interval_s=0.5, max_retries=1),
    'openai/gpt-5.5-pro:batch': ModelRule("openrouter", concurrency=1, min_interval_s=0.5, max_retries=1),
    'openai/gpt-5.5': ModelRule("openrouter", concurrency=1, min_interval_s=0.5, max_retries=1),
    'openai/gpt-5.5:batch': ModelRule("openrouter", concurrency=1, min_interval_s=0.5, max_retries=1),
    'deepseek/deepseek-v4-pro': ModelRule("openrouter", concurrency=1, min_interval_s=0.5, max_retries=1),
    'deepseek/deepseek-v4-flash': ModelRule("openrouter", concurrency=1, min_interval_s=0.5, max_retries=1),
    'tencent/hy3-preview': ModelRule("openrouter", concurrency=1, min_interval_s=0.5, max_retries=1),
    'xiaomi/mimo-v2.5-pro': ModelRule("openrouter", concurrency=1, min_interval_s=0.5, max_retries=1),
    'xiaomi/mimo-v2.5': ModelRule("openrouter", concurrency=1, min_interval_s=0.5, max_retries=1),
    'openai/gpt-5.4-image-2': ModelRule("openrouter", concurrency=1, min_interval_s=0.5, max_retries=1),
    '~anthropic/claude-opus-latest': ModelRule("openrouter", concurrency=1, min_interval_s=0.5, max_retries=1),
    'moonshotai/kimi-k2.6': ModelRule("openrouter", concurrency=1, min_interval_s=0.5, max_retries=1),
    'anthropic/claude-opus-4.7': ModelRule("openrouter", concurrency=1, min_interval_s=0.5, max_retries=1),
    'anthropic/claude-opus-4.7:batch': ModelRule("openrouter", concurrency=1, min_interval_s=0.5, max_retries=1),
    'z-ai/glm-5.1': ModelRule("openrouter", concurrency=1, min_interval_s=0.5, max_retries=1),
    'google/gemma-4-26b-a4b-it': ModelRule("openrouter", concurrency=1, min_interval_s=0.5, max_retries=1),
    'google/gemma-4-26b-a4b-it:free': ModelRule("openrouter", concurrency=1, min_interval_s=0.5, max_retries=1),
    'google/gemma-4-31b-it': ModelRule("openrouter", concurrency=1, min_interval_s=0.5, max_retries=1),
    'google/gemma-4-31b-it:free': ModelRule("openrouter", concurrency=1, min_interval_s=0.5, max_retries=1),
    'qwen/qwen3.6-plus': ModelRule("openrouter", concurrency=1, min_interval_s=0.5, max_retries=1),
    'z-ai/glm-5v-turbo': ModelRule("openrouter", concurrency=1, min_interval_s=0.5, max_retries=1),
    'x-ai/grok-4.20-multi-agent': ModelRule("openrouter", concurrency=1, min_interval_s=0.5, max_retries=1),
    'x-ai/grok-4.20': ModelRule("openrouter", concurrency=1, min_interval_s=0.5, max_retries=1),
    'google/lyria-3-pro-preview': ModelRule("openrouter", concurrency=1, min_interval_s=0.5, max_retries=1),
    'google/lyria-3-clip-preview': ModelRule("openrouter", concurrency=1, min_interval_s=0.5, max_retries=1),
    'rekaai/reka-edge': ModelRule("openrouter", concurrency=1, min_interval_s=0.5, max_retries=1),
    'minimax/minimax-m2.7': ModelRule("openrouter", concurrency=1, min_interval_s=0.5, max_retries=1),
    'openai/gpt-5.4-nano': ModelRule("openrouter", concurrency=1, min_interval_s=0.5, max_retries=1),
    'openai/gpt-5.4-nano:batch': ModelRule("openrouter", concurrency=1, min_interval_s=0.5, max_retries=1),
    'openai/gpt-5.4-mini': ModelRule("openrouter", concurrency=1, min_interval_s=0.5, max_retries=1),
    'openai/gpt-5.4-mini:batch': ModelRule("openrouter", concurrency=1, min_interval_s=0.5, max_retries=1),
    'mistralai/mistral-small-2603': ModelRule("openrouter", concurrency=1, min_interval_s=0.5, max_retries=1),
    'z-ai/glm-5-turbo': ModelRule("openrouter", concurrency=1, min_interval_s=0.5, max_retries=1),
    'nvidia/nemotron-3-super-120b-a12b': ModelRule("openrouter", concurrency=1, min_interval_s=0.5, max_retries=1),
    'bytedance-seed/seed-2.0-lite': ModelRule("openrouter", concurrency=1, min_interval_s=0.5, max_retries=1),
    'qwen/qwen3.5-9b': ModelRule("openrouter", concurrency=1, min_interval_s=0.5, max_retries=1),
    'openai/gpt-5.4-pro': ModelRule("openrouter", concurrency=1, min_interval_s=0.5, max_retries=1),
    'openai/gpt-5.4-pro:batch': ModelRule("openrouter", concurrency=1, min_interval_s=0.5, max_retries=1),
    'openai/gpt-5.4': ModelRule("openrouter", concurrency=1, min_interval_s=0.5, max_retries=1),
    'openai/gpt-5.4:batch': ModelRule("openrouter", concurrency=1, min_interval_s=0.5, max_retries=1),
    'google/gemini-3.1-flash-lite-preview': ModelRule("openrouter", concurrency=1, min_interval_s=0.5, max_retries=1),
    'bytedance-seed/seed-2.0-mini': ModelRule("openrouter", concurrency=1, min_interval_s=0.5, max_retries=1),
    'google/gemini-3.1-flash-image-preview': ModelRule("openrouter", concurrency=1, min_interval_s=0.5, max_retries=1),
    'qwen/qwen3.5-35b-a3b': ModelRule("openrouter", concurrency=1, min_interval_s=0.5, max_retries=1),
    'qwen/qwen3.5-27b': ModelRule("openrouter", concurrency=1, min_interval_s=0.5, max_retries=1),
    'qwen/qwen3.5-122b-a10b': ModelRule("openrouter", concurrency=1, min_interval_s=0.5, max_retries=1),
    'qwen/qwen3.5-flash-02-23': ModelRule("openrouter", concurrency=1, min_interval_s=0.5, max_retries=1),
    'google/gemini-3.1-pro-preview-customtools': ModelRule("openrouter", concurrency=1, min_interval_s=0.5, max_retries=1),
    'openai/gpt-5.3-codex': ModelRule("openrouter", concurrency=1, min_interval_s=0.5, max_retries=1),
    'aion-labs/aion-2.0': ModelRule("openrouter", concurrency=1, min_interval_s=0.5, max_retries=1),
    'google/gemini-3.1-pro-preview': ModelRule("openrouter", concurrency=1, min_interval_s=0.5, max_retries=1),
    'google/gemini-3.1-pro-preview:batch': ModelRule("openrouter", concurrency=1, min_interval_s=0.5, max_retries=1),
    'anthropic/claude-sonnet-4.6': ModelRule("openrouter", concurrency=1, min_interval_s=0.5, max_retries=1),
    'anthropic/claude-sonnet-4.6:batch': ModelRule("openrouter", concurrency=1, min_interval_s=0.5, max_retries=1),
    'qwen/qwen3.5-plus-02-15': ModelRule("openrouter", concurrency=1, min_interval_s=0.5, max_retries=1),
    'qwen/qwen3.5-397b-a17b': ModelRule("openrouter", concurrency=1, min_interval_s=0.5, max_retries=1),
    'minimax/minimax-m2.5': ModelRule("openrouter", concurrency=1, min_interval_s=0.5, max_retries=1),
    'z-ai/glm-5': ModelRule("openrouter", concurrency=1, min_interval_s=0.5, max_retries=1),
    'anthropic/claude-opus-4.6': ModelRule("openrouter", concurrency=1, min_interval_s=0.5, max_retries=1),
    'anthropic/claude-opus-4.6:batch': ModelRule("openrouter", concurrency=1, min_interval_s=0.5, max_retries=1),
    'qwen/qwen3-coder-next': ModelRule("openrouter", concurrency=1, min_interval_s=0.5, max_retries=1),
    'stepfun/step-3.5-flash': ModelRule("openrouter", concurrency=1, min_interval_s=0.5, max_retries=1),
    'moonshotai/kimi-k2.5': ModelRule("openrouter", concurrency=1, min_interval_s=0.5, max_retries=1),
    'writer/palmyra-x5': ModelRule("openrouter", concurrency=1, min_interval_s=0.5, max_retries=1),
    'openai/gpt-audio': ModelRule("openrouter", concurrency=1, min_interval_s=0.5, max_retries=1),
    'openai/gpt-audio-mini': ModelRule("openrouter", concurrency=1, min_interval_s=0.5, max_retries=1),
    'z-ai/glm-4.7-flash': ModelRule("openrouter", concurrency=1, min_interval_s=0.5, max_retries=1),
    'openai/gpt-5.2-codex': ModelRule("openrouter", concurrency=1, min_interval_s=0.5, max_retries=1),
    'z-ai/glm-4.7': ModelRule("openrouter", concurrency=1, min_interval_s=0.5, max_retries=1),
    'google/gemini-3-flash-preview': ModelRule("openrouter", concurrency=1, min_interval_s=0.5, max_retries=1),
    'google/gemini-3-flash-preview:batch': ModelRule("openrouter", concurrency=1, min_interval_s=0.5, max_retries=1),
    'nvidia/nemotron-3-nano-30b-a3b': ModelRule("openrouter", concurrency=1, min_interval_s=0.5, max_retries=1),
    'openai/gpt-5.2-chat': ModelRule("openrouter", concurrency=1, min_interval_s=0.5, max_retries=1),
    'openai/gpt-5.2-pro': ModelRule("openrouter", concurrency=1, min_interval_s=0.5, max_retries=1),
    'openai/gpt-5.2-pro:batch': ModelRule("openrouter", concurrency=1, min_interval_s=0.5, max_retries=1),
    'openai/gpt-5.2': ModelRule("openrouter", concurrency=1, min_interval_s=0.5, max_retries=1),
    'openai/gpt-5.2:batch': ModelRule("openrouter", concurrency=1, min_interval_s=0.5, max_retries=1),
    'mistralai/devstral-2512': ModelRule("openrouter", concurrency=1, min_interval_s=0.5, max_retries=1),
    'relace/relace-search': ModelRule("openrouter", concurrency=1, min_interval_s=0.5, max_retries=1),
    'z-ai/glm-4.6v': ModelRule("openrouter", concurrency=1, min_interval_s=0.5, max_retries=1),
    'openai/gpt-5.1-codex-max': ModelRule("openrouter", concurrency=1, min_interval_s=0.5, max_retries=1),
    'amazon/nova-2-lite-v1': ModelRule("openrouter", concurrency=1, min_interval_s=0.5, max_retries=1),
    'mistralai/ministral-14b-2512': ModelRule("openrouter", concurrency=1, min_interval_s=0.5, max_retries=1),
    'mistralai/ministral-8b-2512': ModelRule("openrouter", concurrency=1, min_interval_s=0.5, max_retries=1),
    'mistralai/ministral-3b-2512': ModelRule("openrouter", concurrency=1, min_interval_s=0.5, max_retries=1),
    'mistralai/mistral-large-2512': ModelRule("openrouter", concurrency=1, min_interval_s=0.5, max_retries=1),
    'deepseek/deepseek-v3.2': ModelRule("openrouter", concurrency=1, min_interval_s=0.5, max_retries=1),
    'anthropic/claude-opus-4.5': ModelRule("openrouter", concurrency=1, min_interval_s=0.5, max_retries=1),
    'anthropic/claude-opus-4.5:batch': ModelRule("openrouter", concurrency=1, min_interval_s=0.5, max_retries=1),
    'google/gemini-3-pro-image-preview': ModelRule("openrouter", concurrency=1, min_interval_s=0.5, max_retries=1),
    'openai/gpt-5.1': ModelRule("openrouter", concurrency=1, min_interval_s=0.5, max_retries=1),
    'openai/gpt-5.1:batch': ModelRule("openrouter", concurrency=1, min_interval_s=0.5, max_retries=1),
    'openai/gpt-5.1-codex': ModelRule("openrouter", concurrency=1, min_interval_s=0.5, max_retries=1),
    'openai/gpt-5.1-codex-mini': ModelRule("openrouter", concurrency=1, min_interval_s=0.5, max_retries=1),
    'moonshotai/kimi-k2-thinking': ModelRule("openrouter", concurrency=1, min_interval_s=0.5, max_retries=1),
    'amazon/nova-premier-v1': ModelRule("openrouter", concurrency=1, min_interval_s=0.5, max_retries=1),
    'perplexity/sonar-pro-search': ModelRule("openrouter", concurrency=1, min_interval_s=0.5, max_retries=1),
    'mistralai/voxtral-small-24b-2507': ModelRule("openrouter", concurrency=1, min_interval_s=0.5, max_retries=1),
    'openai/gpt-oss-safeguard-20b': ModelRule("openrouter", concurrency=1, min_interval_s=0.5, max_retries=1),
    'openai/gpt-5-image-mini': ModelRule("openrouter", concurrency=1, min_interval_s=0.5, max_retries=1),
    'anthropic/claude-haiku-4.5': ModelRule("openrouter", concurrency=1, min_interval_s=0.5, max_retries=1),
    'anthropic/claude-haiku-4.5:batch': ModelRule("openrouter", concurrency=1, min_interval_s=0.5, max_retries=1),
    'qwen/qwen3-vl-8b-instruct': ModelRule("openrouter", concurrency=1, min_interval_s=0.5, max_retries=1),
    'openai/gpt-5-image': ModelRule("openrouter", concurrency=1, min_interval_s=0.5, max_retries=1),
    'google/gemini-2.5-flash-image': ModelRule("openrouter", concurrency=1, min_interval_s=0.5, max_retries=1),
    'qwen/qwen3-vl-30b-a3b-thinking': ModelRule("openrouter", concurrency=1, min_interval_s=0.5, max_retries=1),
    'qwen/qwen3-vl-30b-a3b-instruct': ModelRule("openrouter", concurrency=1, min_interval_s=0.5, max_retries=1),
    'openai/gpt-5-pro': ModelRule("openrouter", concurrency=1, min_interval_s=0.5, max_retries=1),
    'openai/gpt-5-pro:batch': ModelRule("openrouter", concurrency=1, min_interval_s=0.5, max_retries=1),
    'z-ai/glm-4.6': ModelRule("openrouter", concurrency=1, min_interval_s=0.5, max_retries=1),
    'anthropic/claude-sonnet-4.5': ModelRule("openrouter", concurrency=1, min_interval_s=0.5, max_retries=1),
    'anthropic/claude-sonnet-4.5:batch': ModelRule("openrouter", concurrency=1, min_interval_s=0.5, max_retries=1),
    'deepseek/deepseek-v3.2-exp': ModelRule("openrouter", concurrency=1, min_interval_s=0.5, max_retries=1),
    'thedrummer/cydonia-24b-v4.1': ModelRule("openrouter", concurrency=1, min_interval_s=0.5, max_retries=1),
    'relace/relace-apply-3': ModelRule("openrouter", concurrency=1, min_interval_s=0.5, max_retries=1),
    'qwen/qwen3-vl-235b-a22b-instruct': ModelRule("openrouter", concurrency=1, min_interval_s=0.5, max_retries=1),
    'deepseek/deepseek-v3.1-terminus': ModelRule("openrouter", concurrency=1, min_interval_s=0.5, max_retries=1),
    'qwen/qwen3-coder-flash': ModelRule("openrouter", concurrency=1, min_interval_s=0.5, max_retries=1),
    'qwen/qwen3-next-80b-a3b-instruct': ModelRule("openrouter", concurrency=1, min_interval_s=0.5, max_retries=1),
    'moonshotai/kimi-k2-0905': ModelRule("openrouter", concurrency=1, min_interval_s=0.5, max_retries=1),
    'nousresearch/hermes-4-405b': ModelRule("openrouter", concurrency=1, min_interval_s=0.5, max_retries=1),
    'deepseek/deepseek-chat-v3.1': ModelRule("openrouter", concurrency=1, min_interval_s=0.5, max_retries=1),
    'mistralai/mistral-medium-3.1': ModelRule("openrouter", concurrency=1, min_interval_s=0.5, max_retries=1),
    'z-ai/glm-4.5v': ModelRule("openrouter", concurrency=1, min_interval_s=0.5, max_retries=1),
    'openai/gpt-5': ModelRule("openrouter", concurrency=1, min_interval_s=0.5, max_retries=1),
    'openai/gpt-5:batch': ModelRule("openrouter", concurrency=1, min_interval_s=0.5, max_retries=1),
    'openai/gpt-5-mini': ModelRule("openrouter", concurrency=1, min_interval_s=0.5, max_retries=1),
    'openai/gpt-5-mini:batch': ModelRule("openrouter", concurrency=1, min_interval_s=0.5, max_retries=1),
    'openai/gpt-5-nano': ModelRule("openrouter", concurrency=1, min_interval_s=0.5, max_retries=1),
    'openai/gpt-5-nano:batch': ModelRule("openrouter", concurrency=1, min_interval_s=0.5, max_retries=1),
    'openai/gpt-oss-120b': ModelRule("openrouter", concurrency=1, min_interval_s=0.5, max_retries=1),
    'openai/gpt-oss-120b:batch': ModelRule("openrouter", concurrency=1, min_interval_s=0.5, max_retries=1),
    'openai/gpt-oss-20b': ModelRule("openrouter", concurrency=1, min_interval_s=0.5, max_retries=1),
    'openai/gpt-oss-20b:batch': ModelRule("openrouter", concurrency=1, min_interval_s=0.5, max_retries=1),
    'anthropic/claude-opus-4.1': ModelRule("openrouter", concurrency=1, min_interval_s=0.5, max_retries=1),
    'anthropic/claude-opus-4.1:batch': ModelRule("openrouter", concurrency=1, min_interval_s=0.5, max_retries=1),
    'mistralai/codestral-2508': ModelRule("openrouter", concurrency=1, min_interval_s=0.5, max_retries=1),
    'qwen/qwen3-coder-30b-a3b-instruct': ModelRule("openrouter", concurrency=1, min_interval_s=0.5, max_retries=1),
    'qwen/qwen3-30b-a3b-instruct-2507': ModelRule("openrouter", concurrency=1, min_interval_s=0.5, max_retries=1),
    'z-ai/glm-4.5': ModelRule("openrouter", concurrency=1, min_interval_s=0.5, max_retries=1),
    'z-ai/glm-4.5-air': ModelRule("openrouter", concurrency=1, min_interval_s=0.5, max_retries=1),
    'qwen/qwen3-235b-a22b-thinking-2507': ModelRule("openrouter", concurrency=1, min_interval_s=0.5, max_retries=1),
    'qwen/qwen3-coder': ModelRule("openrouter", concurrency=1, min_interval_s=0.5, max_retries=1),
    'bytedance/ui-tars-1.5-7b': ModelRule("openrouter", concurrency=1, min_interval_s=0.5, max_retries=1),
    'google/gemini-2.5-flash-lite': ModelRule("openrouter", concurrency=1, min_interval_s=0.5, max_retries=1),
    'qwen/qwen3-235b-a22b-2507': ModelRule("openrouter", concurrency=1, min_interval_s=0.5, max_retries=1),
    'moonshotai/kimi-k2': ModelRule("openrouter", concurrency=1, min_interval_s=0.5, max_retries=1),
    'cognitivecomputations/dolphin-mistral-24b-venice-edition': ModelRule("openrouter", concurrency=1, min_interval_s=0.5, max_retries=1),
    'tencent/hunyuan-a13b-instruct': ModelRule("openrouter", concurrency=1, min_interval_s=0.5, max_retries=1),
    'morph/morph-v3-large': ModelRule("openrouter", concurrency=1, min_interval_s=0.5, max_retries=1),
    'morph/morph-v3-large:batch': ModelRule("openrouter", concurrency=1, min_interval_s=0.5, max_retries=1),
    'morph/morph-v3-fast': ModelRule("openrouter", concurrency=1, min_interval_s=0.5, max_retries=1),
    'morph/morph-v3-fast:batch': ModelRule("openrouter", concurrency=1, min_interval_s=0.5, max_retries=1),
    'mistralai/mistral-small-3.2-24b-instruct': ModelRule("openrouter", concurrency=1, min_interval_s=0.5, max_retries=1),
    'google/gemini-2.5-flash': ModelRule("openrouter", concurrency=1, min_interval_s=0.5, max_retries=1),
    'google/gemini-2.5-pro': ModelRule("openrouter", concurrency=1, min_interval_s=0.5, max_retries=1),
    'openai/o3-pro': ModelRule("openrouter", concurrency=1, min_interval_s=0.5, max_retries=1),
    'google/gemini-2.5-pro-preview': ModelRule("openrouter", concurrency=1, min_interval_s=0.5, max_retries=1),
    'deepseek/deepseek-r1-0528': ModelRule("openrouter", concurrency=1, min_interval_s=0.5, max_retries=1),
    'mistralai/mistral-medium-3': ModelRule("openrouter", concurrency=1, min_interval_s=0.5, max_retries=1),
    'meta-llama/llama-guard-4-12b': ModelRule("openrouter", concurrency=1, min_interval_s=0.5, max_retries=1),
    'qwen/qwen3-30b-a3b': ModelRule("openrouter", concurrency=1, min_interval_s=0.5, max_retries=1),
    'qwen/qwen3-14b': ModelRule("openrouter", concurrency=1, min_interval_s=0.5, max_retries=1),
    'qwen/qwen3-32b': ModelRule("openrouter", concurrency=1, min_interval_s=0.5, max_retries=1),
    'openai/o3': ModelRule("openrouter", concurrency=1, min_interval_s=0.5, max_retries=1),
    'openai/o3:batch': ModelRule("openrouter", concurrency=1, min_interval_s=0.5, max_retries=1),
    'openai/o4-mini:batch': ModelRule("openrouter", concurrency=1, min_interval_s=0.5, max_retries=1),
    'openai/gpt-4.1': ModelRule("openrouter", concurrency=1, min_interval_s=0.5, max_retries=1),
    'openai/gpt-4.1:batch': ModelRule("openrouter", concurrency=1, min_interval_s=0.5, max_retries=1),
    'openai/gpt-4.1-mini': ModelRule("openrouter", concurrency=1, min_interval_s=0.5, max_retries=1),
    'openai/gpt-4.1-mini:batch': ModelRule("openrouter", concurrency=1, min_interval_s=0.5, max_retries=1),
    'openai/gpt-4.1-nano': ModelRule("openrouter", concurrency=1, min_interval_s=0.5, max_retries=1),
    'openai/gpt-4.1-nano:batch': ModelRule("openrouter", concurrency=1, min_interval_s=0.5, max_retries=1),
    'meta-llama/llama-4-maverick': ModelRule("openrouter", concurrency=1, min_interval_s=0.5, max_retries=1),
    'meta-llama/llama-4-scout': ModelRule("openrouter", concurrency=1, min_interval_s=0.5, max_retries=1),
    'deepseek/deepseek-chat-v3-0324': ModelRule("openrouter", concurrency=1, min_interval_s=0.5, max_retries=1),
    'mistralai/mistral-small-3.1-24b-instruct': ModelRule("openrouter", concurrency=1, min_interval_s=0.5, max_retries=1),
    'google/gemma-3-4b-it': ModelRule("openrouter", concurrency=1, min_interval_s=0.5, max_retries=1),
    'google/gemma-3-12b-it': ModelRule("openrouter", concurrency=1, min_interval_s=0.5, max_retries=1),
    'cohere/command-a': ModelRule("openrouter", concurrency=1, min_interval_s=0.5, max_retries=1),
    'rekaai/reka-flash-3': ModelRule("openrouter", concurrency=1, min_interval_s=0.5, max_retries=1),
    'google/gemma-3-27b-it': ModelRule("openrouter", concurrency=1, min_interval_s=0.5, max_retries=1),
    'thedrummer/skyfall-36b-v2': ModelRule("openrouter", concurrency=1, min_interval_s=0.5, max_retries=1),
    'perplexity/sonar-reasoning-pro': ModelRule("openrouter", concurrency=1, min_interval_s=0.5, max_retries=1),
    'perplexity/sonar-pro': ModelRule("openrouter", concurrency=1, min_interval_s=0.5, max_retries=1),
    'perplexity/sonar-deep-research': ModelRule("openrouter", concurrency=1, min_interval_s=0.5, max_retries=1),
    'mistralai/mistral-saba': ModelRule("openrouter", concurrency=1, min_interval_s=0.5, max_retries=1),
    'aion-labs/aion-rp-llama-3.1-8b': ModelRule("openrouter", concurrency=1, min_interval_s=0.5, max_retries=1),
    'qwen/qwen2.5-vl-72b-instruct': ModelRule("openrouter", concurrency=1, min_interval_s=0.5, max_retries=1),
    'qwen/qwen-plus': ModelRule("openrouter", concurrency=1, min_interval_s=0.5, max_retries=1),
    'openai/o3-mini:batch': ModelRule("openrouter", concurrency=1, min_interval_s=0.5, max_retries=1),
    'mistralai/mistral-small-24b-instruct-2501': ModelRule("openrouter", concurrency=1, min_interval_s=0.5, max_retries=1),
    'perplexity/sonar': ModelRule("openrouter", concurrency=1, min_interval_s=0.5, max_retries=1),
    'microsoft/phi-4': ModelRule("openrouter", concurrency=1, min_interval_s=0.5, max_retries=1),
    'deepseek/deepseek-chat': ModelRule("openrouter", concurrency=1, min_interval_s=0.5, max_retries=1),
    'cohere/command-r7b-12-2024': ModelRule("openrouter", concurrency=1, min_interval_s=0.5, max_retries=1),
    'meta-llama/llama-3.3-70b-instruct': ModelRule("openrouter", concurrency=1, min_interval_s=0.5, max_retries=1),
    'amazon/nova-lite-v1': ModelRule("openrouter", concurrency=1, min_interval_s=0.5, max_retries=1),
    'amazon/nova-micro-v1': ModelRule("openrouter", concurrency=1, min_interval_s=0.5, max_retries=1),
    'amazon/nova-pro-v1': ModelRule("openrouter", concurrency=1, min_interval_s=0.5, max_retries=1),
    'openai/gpt-4o-2024-11-20': ModelRule("openrouter", concurrency=1, min_interval_s=0.5, max_retries=1),
    'mistralai/mistral-large-2407': ModelRule("openrouter", concurrency=1, min_interval_s=0.5, max_retries=1),
    'qwen/qwen-2.5-coder-32b-instruct': ModelRule("openrouter", concurrency=1, min_interval_s=0.5, max_retries=1),
    'thedrummer/unslopnemo-12b': ModelRule("openrouter", concurrency=1, min_interval_s=0.5, max_retries=1),
    'anthracite-org/magnum-v4-72b': ModelRule("openrouter", concurrency=1, min_interval_s=0.5, max_retries=1),
    'meta-llama/llama-3.2-1b-instruct': ModelRule("openrouter", concurrency=1, min_interval_s=0.5, max_retries=1),
    'meta-llama/llama-3.2-3b-instruct': ModelRule("openrouter", concurrency=1, min_interval_s=0.5, max_retries=1),
    'qwen/qwen-2.5-72b-instruct': ModelRule("openrouter", concurrency=1, min_interval_s=0.5, max_retries=1),
    'cohere/command-r-08-2024': ModelRule("openrouter", concurrency=1, min_interval_s=0.5, max_retries=1),
    'cohere/command-r-plus-08-2024': ModelRule("openrouter", concurrency=1, min_interval_s=0.5, max_retries=1),
    'sao10k/l3.1-euryale-70b': ModelRule("openrouter", concurrency=1, min_interval_s=0.5, max_retries=1),
    'sao10k/l3-lunaris-8b': ModelRule("openrouter", concurrency=1, min_interval_s=0.5, max_retries=1),
    'openai/gpt-4o-2024-08-06': ModelRule("openrouter", concurrency=1, min_interval_s=0.5, max_retries=1),
    'meta-llama/llama-3.1-70b-instruct': ModelRule("openrouter", concurrency=1, min_interval_s=0.5, max_retries=1),
    'meta-llama/llama-3.1-8b-instruct': ModelRule("openrouter", concurrency=1, min_interval_s=0.5, max_retries=1),
    'mistralai/mistral-nemo': ModelRule("openrouter", concurrency=1, min_interval_s=0.5, max_retries=1),
    'openai/gpt-4o-mini': ModelRule("openrouter", concurrency=1, min_interval_s=0.5, max_retries=1),
    'openai/gpt-4o-mini-2024-07-18': ModelRule("openrouter", concurrency=1, min_interval_s=0.5, max_retries=1),
    'openai/gpt-4o-mini:batch': ModelRule("openrouter", concurrency=1, min_interval_s=0.5, max_retries=1),
    'google/gemma-2-27b-it': ModelRule("openrouter", concurrency=1, min_interval_s=0.5, max_retries=1),
    'openai/gpt-4o': ModelRule("openrouter", concurrency=1, min_interval_s=0.5, max_retries=1),
    'openai/gpt-4o-2024-05-13': ModelRule("openrouter", concurrency=1, min_interval_s=0.5, max_retries=1),
    'openai/gpt-4o:batch': ModelRule("openrouter", concurrency=1, min_interval_s=0.5, max_retries=1),
    'mistralai/mixtral-8x22b-instruct': ModelRule("openrouter", concurrency=1, min_interval_s=0.5, max_retries=1),
    'openai/gpt-4-turbo:batch': ModelRule("openrouter", concurrency=1, min_interval_s=0.5, max_retries=1),
    'mistralai/mistral-large': ModelRule("openrouter", concurrency=1, min_interval_s=0.5, max_retries=1),
    'openai/gpt-3.5-turbo-0613': ModelRule("openrouter", concurrency=1, min_interval_s=0.5, max_retries=1),
    'openai/gpt-3.5-turbo-16k': ModelRule("openrouter", concurrency=1, min_interval_s=0.5, max_retries=1),
    'mancer/weaver': ModelRule("openrouter", concurrency=1, min_interval_s=0.5, max_retries=1),
    'undi95/remm-slerp-l2-13b': ModelRule("openrouter", concurrency=1, min_interval_s=0.5, max_retries=1),
    'gryphe/mythomax-l2-13b': ModelRule("openrouter", concurrency=1, min_interval_s=0.5, max_retries=1),
    'openai/gpt-4': ModelRule("openrouter", concurrency=1, min_interval_s=0.5, max_retries=1),
    'openrouter/free': ModelRule("openrouter", concurrency=1, min_interval_s=0.5, max_retries=1),
    # xAI fast tiers.
    "grok-4.20-0309-non-reasoning": ModelRule("xai", concurrency=3),
    "grok-build-0.1": ModelRule("xai", concurrency=3),
    "grok-4.20-multi-agent-0309": ModelRule("xai", concurrency=1),
    "grok-4.20-0309-reasoning": ModelRule("xai", concurrency=2),
    "grok-4.20": ModelRule("xai", concurrency=2),
    # Anthropic — Haiku is the junior/commodity tier; Sonnet/Opus are
    # deliberative seats first, chain tails only by explicit design.
    "claude-haiku-5-5": ModelRule("anthropic", concurrency=3),
    "claude-sonnet-5-5": ModelRule("anthropic", concurrency=2),
    "claude-opus-5-5": ModelRule("anthropic", concurrency=1),
    "claude-fable-5-2": ModelRule("anthropic", concurrency=1),
    # OpenAI-compatible + local lanes.
    "gpt-5": ModelRule("openai", concurrency=2),
    "gpt-5-mini": ModelRule("openai", concurrency=3),
    "qwen3:14b": ModelRule("local", concurrency=1),
    "deepseek-r1:14b": ModelRule("local", concurrency=1),
    "llama3.1:8b": ModelRule("local", concurrency=1),
}

RETIRED_MODELS = {
    "gemini-2.5-flash": "retired 2026-11-12 (his evidence: superseded by 3.8-flash; do not dispatch)",
}

# Loop classes — the SLO axis (schema v1.1): panel · commission ·
# junior · ruling · defect · lower-order. Behavior is gate-internal:
# "degrade" walks the class chain on a budget breach; "fail-closed"
# stops. Chain order is the degrade order. The dispatch record
# carries the SLO class only; legacy caller names normalize onto it.
# R-1 pin (C-023, 2026-11-12): gemini-3.6-flash requested DIRECT is
# the commodity workhorse pin (chain head). gemini-3.8-flash leaves
# the chain (BENCH probation, R-2). A commodity request naming
# gemini-3.5-flash re-pins to the pin at resolve (see REPINS).
# v0.1 spread extension (2026-11-17, his routing-spread directive;
# gate v0.4.29): the two PROVEN OpenRouter free seats join the chain
# behind the pin. The C-042 live-cost re-rank prices them at $0, so
# they take degradable volume on price; the pin keeps the static
# head and the direct-request re-pin. Claude falls to last resort.
COMMODITY_CHAIN = [
    "gemini-3.6-flash",
    "nemotron-3-ultra",
    "north-mini-code",
    "grok-4.20-0309-non-reasoning",
    "claude-haiku-5-5",
]

# Re-pins at preflight (C-023 R-1): requested -> pin, labeled on the
# record via Resolution.note + degraded_from. The source id keeps
# only its labeled LC-3 panel-voice role (deliberative classes fire
# it as requested — the re-pin binds commodity classes only).
REPINS = {"gemini-3.5-flash": "gemini-3.6-flash"}

# Lane holds (operational, 2026-11-17): a provider whose credential
# is invalid at the provider gets NO service dispatch — every seat
# on the lane stops as banned with the reason on the record, in
# every loop class, until a proof passes and the entry is removed
# (the lift is this one entry, changed on the record). Measurement
# (seat_mode named) is exempt, per the GL-15 pattern: the canary
# and the credential proof must still be able to probe the lane.
# History: the xAI entry stood 2026-11-17 ~11:5x–12:54 CT (stored
# value was a wrapped/truncated copy, not an xAI key) and was
# LIFTED when the /v1/models proof passed on custom.grok (CoS
# handoff 12:54 CT; the raw console key passes). The registry is
# empty at rest; the mechanism stays for the next dead lane.
LANE_HOLDS: dict[str, str] = {}


def lane_hold(model: str) -> str | None:
    """The hold reason when the model's provider lane is held."""
    rule = MODELS.get(model)
    if rule is None:
        return None
    return LANE_HOLDS.get(rule.provider)

# ---------------------------------------------------------------------------
# Class-priority queue (C-026 line 1)
#
# When a model's slots are contended, waiting dispatches register
# in the throttle state and take the slot in priority order — the
# blind poll race is gone. Priority = the SLO class rank, improved
# by aging so a low class cannot starve under steady contention:
# effective rank drops 1 per AGE_STEP_S waited, floored at 0. Ties
# break by enqueue time. v1 calibration (AGE_STEP_S = 45 s): a
# lower-order waiter reaches effective rank 0 in 225 s, inside the
# cold-lane acquire budget; the burn reads tune the step.

CLASS_RANK = {
    "ruling": 0,
    "commission": 1,
    "panel": 2,
    # v0.4.35: the draft-check loop gates outward sends — a desk
    # waits on the verdict — so it ranks with the panel class.
    "draft-check": 2,
    "junior": 3,
    "defect": 4,
    "lower-order": 5,
}
AGE_STEP_S = 45.0
QUEUE_STALE_S = 600.0


def effective_rank(loop_class: str, waited_s: float) -> int:
    rank = CLASS_RANK[normalize_class(loop_class)]
    return max(0, rank - int(waited_s // AGE_STEP_S))


# Probation (C-023 R-2): a model in this set that breaches its
# error budget is quarantined in state on the spot — one provider-
# error cluster ends the probation (Argon's full position executes
# on that event). Quarantine = the gate stops the id as banned.
# GL-15 (C-030, rule text): probation scope reads SERVICE-ONLY.
# Measurement (seat_mode named) is exempt by rule: a named run is
# never blocked by the quarantine, and its errors never set it.
PROBATION_MODELS = {"gemini-3.8-flash"}

LOOP_CLASSES: dict[str, dict] = {
    "panel": {"behavior": "fail-closed", "chain": []},
    "commission": {"behavior": "fail-closed", "chain": []},
    "ruling": {"behavior": "fail-closed", "chain": []},
    # Designated-seat service (v0.4.35, AR-20261117-06): the
    # outward-draft compliance check fires its checker seat or
    # stops — substitution would be a different gate.
    "draft-check": {"behavior": "fail-closed", "chain": []},
    "junior": {"behavior": "degrade", "chain": COMMODITY_CHAIN},
    "defect": {"behavior": "degrade", "chain": COMMODITY_CHAIN},
    "lower-order": {"behavior": "degrade", "chain": COMMODITY_CHAIN},
}

CLASS_ALIASES = {
    "junior-panel": "junior",
    "sweep": "lower-order",
    "scan": "lower-order",
    "mechanical": "lower-order",
    "enrichment": "lower-order",
    "council": "ruling",
    "seat": "ruling",
    "deliberative": "ruling",
}

DEFAULT_LOOP_CLASS = "ruling"  # unknown classes fail closed


def normalize_class(loop_class: str) -> str:
    if loop_class in LOOP_CLASSES:
        return loop_class
    return CLASS_ALIASES.get(loop_class, DEFAULT_LOOP_CLASS)


class ThrottleError(Exception):
    """Base for gate refusals raised by the throttle layer."""


class BannedModel(ThrottleError):
    pass


class BudgetBreached(ThrottleError):
    pass


@dataclass
class Resolution:
    model: str
    degraded_from: str | None = None
    chain: list = field(default_factory=list)
    note: str | None = None


# ---------------------------------------------------------------- state

class ThrottleState:
    """JSON-backed per-model throttle state with a lockfile."""

    def __init__(self, path: str):
        self.path = path
        self.lock_path = path + ".lock"

    def _load(self) -> dict:
        if os.path.exists(self.path):
            with open(self.path, encoding="utf-8") as fh:
                return json.load(fh)
        return {}

    def _save(self, data: dict) -> None:
        tmp = self.path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as fh:
            json.dump(data, fh, sort_keys=True)
        os.replace(tmp, self.path)

    def mutate(self, fn):
        """Run fn(data) under the lockfile; persist; return fn's value."""
        deadline = time.monotonic() + 30.0
        fd = None
        while fd is None:
            try:
                fd = os.open(self.lock_path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
            except FileExistsError:
                if time.monotonic() > deadline:
                    raise ThrottleError("throttle state lock timeout")
                time.sleep(0.05)
        try:
            data = self._load()
            result = fn(data)
            self._save(data)
            return result
        finally:
            os.close(fd)
            try:
                os.unlink(self.lock_path)
            except FileNotFoundError:
                pass

    # -- queries ------------------------------------------------------
    def budget_breached(self, model: str, now: float) -> bool:
        rule = MODELS[model]
        data = self._load()
        entry = data.get(model, {})
        if entry.get("cooldown_until", 0.0) > now:
            return True
        window = [t for t in entry.get("errors", []) if now - t < rule.error_window_s]
        return len(window) >= rule.error_budget

    def in_flight(self, model: str) -> int:
        return int(self._load().get(model, {}).get("in_flight", 0))

    # -- mutations ----------------------------------------------------
    def record_error(self, model: str, now: float,
                     probation_exempt: bool = False) -> bool:
        """Append an error; set cooldown if the budget just breached."""
        rule = MODELS[model]

        def _fn(data):
            entry = data.setdefault(model, {"errors": [], "in_flight": 0})
            entry["errors"] = [
                t for t in entry.get("errors", []) if now - t < rule.error_window_s
            ] + [now]
            breached = len(entry["errors"]) >= rule.error_budget
            if breached:
                entry["cooldown_until"] = now + rule.cooldown_s
                entry["breach_count"] = entry.get("breach_count", 0) + 1
                if model in PROBATION_MODELS and not probation_exempt:
                    entry["quarantined"] = True
            return breached

        return self.mutate(_fn)

    def queue_snapshot(self, model: str, now: float) -> list:
        """Live queue entries for a model, in grant order."""
        data = self._load()
        entries = [
            e for e in data.get(model, {}).get("queue", [])
            if now - float(e["at"]) <= QUEUE_STALE_S
        ]
        return sorted(
            entries,
            key=lambda e: (
                effective_rank(e["cls"], now - float(e["at"])),
                float(e["at"]),
            ),
        )

    def enqueue(self, model: str, waiter: str, loop_class: str, now: float) -> None:
        def _fn(data):
            entry = data.setdefault(model, {"errors": [], "in_flight": 0})
            queue = [
                e for e in entry.get("queue", [])
                if now - float(e["at"]) <= QUEUE_STALE_S and e["waiter"] != waiter
            ]
            queue.append({"waiter": waiter, "cls": normalize_class(loop_class),
                          "at": now})
            entry["queue"] = queue
            return None
        self.mutate(_fn)

    def dequeue(self, model: str, waiter: str) -> None:
        def _fn(data):
            entry = data.get(model)
            if entry and "queue" in entry:
                entry["queue"] = [e for e in entry["queue"]
                                  if e["waiter"] != waiter]
            return None
        self.mutate(_fn)

    def queue_head(self, model: str, now: float) -> str | None:
        snap = self.queue_snapshot(model, now)
        return snap[0]["waiter"] if snap else None

    def is_quarantined(self, model: str) -> bool:
        data = self._load()
        return bool(data.get(model, {}).get("quarantined"))

    def record_success(self, model: str, now: float) -> None:
        def _fn(data):
            entry = data.setdefault(model, {"errors": [], "in_flight": 0})
            entry["last_success"] = now

        self.mutate(_fn)

    def try_acquire(self, model: str, now: float) -> bool:
        """Take a concurrency slot + stamp the call time, if allowed."""
        rule = MODELS[model]

        def _fn(data):
            entry = data.setdefault(model, {"errors": [], "in_flight": 0})
            if int(entry.get("in_flight", 0)) >= rule.concurrency:
                return False
            if now - float(entry.get("last_call", 0.0)) < rule.min_interval_s:
                return False
            entry["in_flight"] = int(entry.get("in_flight", 0)) + 1
            entry["last_call"] = now
            return True

        return self.mutate(_fn)

    def release(self, model: str) -> None:
        def _fn(data):
            entry = data.setdefault(model, {"errors": [], "in_flight": 0})
            entry["in_flight"] = max(0, int(entry.get("in_flight", 0)) - 1)

        self.mutate(_fn)


# ---------------------------------------------------------------- logic

def check_model(model: str) -> ModelRule:
    """Allowlist + bans. Raises BannedModel with the reason."""
    if "latest" in model:
        raise BannedModel(f"{model}: '-latest' aliases are banned (unpinned model)")
    if model in RETIRED_MODELS:
        raise BannedModel(f"{model}: {RETIRED_MODELS[model]}")
    if model not in MODELS:
        raise BannedModel(f"{model}: not on the throttle allowlist")
    return MODELS[model]


def resolve(loop_class: str, requested: str, state: ThrottleState, now: float,
            seat_mode: str = "chain",
            chain_order: list[str] | None = None) -> Resolution:
    """Pick the model a dispatch actually fires on.

    Deliberative classes get the requested model or a BudgetBreached
    stop. Commodity classes walk their chain from the requested model
    (when it is a chain member) to the first model inside its error
    budget; the walk is the standing designation, and every step off
    the requested model is reported on the Resolution.
    """
    check_model(requested)
    spec = LOOP_CLASSES[normalize_class(loop_class)]
    if seat_mode == "named":
        # Named-seat measurement mode (C-023 build line, 2026-11-12):
        # fire the requested seat as itself, outside the chain, for
        # measurement only. Throttle discipline stays whole; a
        # budget breach stops fail-closed — a substituted return is
        # worthless as a seat measurement, so there is no degrade.
        if state.budget_breached(requested, now):
            raise BudgetBreached(
                f"{requested}: error budget breached; named-seat mode stops (no degrade)"
            )
        return Resolution(model=requested,
                          note="seat_mode: named (measurement)")
    # Service paths only below. GL-15 (C-030): probation scope reads
    # service-only; measurement (seat_mode named) is exempt by rule —
    # the quarantine guard binds service dispatch, never measurement.
    if state.is_quarantined(requested):
        raise BannedModel(
            f"{requested}: quarantined in throttle state (probation trigger fired)"
        )
    _hold = lane_hold(requested)
    if _hold is not None:
        raise BannedModel(f"{requested}: lane held — {_hold}")
    if spec["behavior"] == "fail-closed":
        if state.budget_breached(requested, now):
            raise BudgetBreached(
                f"{requested}: error budget breached; fail-closed class {loop_class!r} stops"
            )
        return Resolution(model=requested)
    # C-042: a live-cost ranking may order the walk. The ranking only
    # reorders eligible chain members — membership, budgets, and
    # containment are unchanged; without it the static chain stands.
    if chain_order:
        members = [m for m in chain_order if m in spec["chain"]]
        members += [m for m in spec["chain"] if m not in members]
        chain = members
    else:
        chain = list(spec["chain"])
    note = None
    effective = requested
    if requested in REPINS:
        effective = REPINS[requested]
        note = f"repinned: {requested} -> {effective} (C-023 R-1)"
    start = chain.index(effective) if effective in chain else 0
    ordered = chain[start:] + chain[:start]
    for candidate in ordered:
        if state.budget_breached(candidate, now) or state.is_quarantined(candidate) \
                or lane_hold(candidate) is not None:
            continue
        return Resolution(
            model=candidate,
            degraded_from=requested if candidate != requested else None,
            chain=ordered,
            note=note,
        )
    raise BudgetBreached(
        f"commodity chain exhausted for class {loop_class!r}: every model over budget"
    )


def backoff_delay(model: str, attempt: int) -> float:
    """Exponential backoff for retry attempt n (0-based)."""
    rule = MODELS[model]
    return min(rule.backoff_base_s * (rule.backoff_factor ** attempt), rule.backoff_max_s)


# C-038: gauntlet quarantine id set (catalog forms). cli refuses these in
# any mode but named (measurement); they enter no chain.
GAUNTLET_IDS = frozenset({'google/gemini-4-hydrogen', 'google/gemini-4-hydrogen:batch', 'baidu/ernie-5.5-flash-preview:free', 'baidu/ernie-light-dt-1.0-intl', 'google/gemini-4-carbon', 'google/gemini-4-carbon:batch', 'nex-agi/nex-n2.6', 'thinkingmachines/inkling-2-small', 'thinkingmachines/inkling-2-small:free', 'anthropic/claude-fable-5.2', 'anthropic/claude-fable-5.2:batch', 'meta/muse-ember', 'liquid/lfm-3-1.7b', 'liquid/lfm-3-1.7b:free', 'google/gemini-omni-1.2-flash', 'kt/midm-k-3.0-pro', 'google/gemini-omni-1.1-flash', 'ricursiveai/ripple-65b-preview', 'tencent/hy4', 'motif-technologies/motif-3', 'z-ai/glm-5.3-flashx-legal', 'particle-ai/particle-1', 'particle-ai/particle-1:free', 'openai/gpt-6.1-terra-pro', 'openai/gpt-6.1-terra-pro:batch', 'openai/gpt-6.1-terra', 'openai/gpt-6.1-terra:batch', 'moonshotai/kimi-k3.1-pro', 'moonshotai/kimi-k3.1-pro:batch', 'recursive/flint-v1.0:free', 'minimax/minimax-m3.1-flash', 'deepseek/deepseek-v4.1-flash-1017', 'deepseek/deepseek-v4.1-flash-1017:batch', 'elorian/glimpse', 'reflection/beam-1.0-501b-a23b', 'prism-ml/ternary-bonsai-2-9b', 'moondream/moondream3-preview', 'moondream/moondream3.1-9b-a2b', 'meta/muse-spark-open', 'nvidia/nemotron-3.5-super-vl', 'nvidia/nemotron-3.5-super-vl:free', 'unbiased/pareto-26.10', '~unbiased/pareto-latest', 'unbiased/pareto-26.9', 'liquid/lfm-2.5-24b-a2b', 'google/gemini-4-argon', 'google/gemini-4-argon:batch', 'scaledown/summarize', 'scaledown/extract', 'meta/muse-wonder', 'stepfun/step-5-preview', 'anthropic/claude-haiku-5.5', 'anthropic/claude-haiku-5.5:batch', 'google/gemini-nano-banana-2.1', 'mistralai/mistral-large-4-0', 'inclusionai/ling-3.1-flash', 'apodex/apodex-1.1-mini:free', 'unbiased/pareto-26.10-preview', 'openai/gpt-6.1-sol-pro', 'openai/gpt-6.1-sol-pro:batch', 'openai/gpt-6.1-sol', 'openai/gpt-6.1-sol:batch', 'anthropic/claude-sonnet-5.5', 'anthropic/claude-sonnet-5.5:batch', 'perceptron/perceptron-mk1.5', 'fireworks/ember-1', 'z-ai/glm-5.3-prime', 'qwen/qwen3.8-max-prime', 'aion-labs/aion-3.5-mini', 'aion-labs/aion-3.5', 'upstage/solar-mini4', 'cohere/command-a-plus', 'openai/gpt-6-luna-pro', 'openai/gpt-6-luna-pro:batch', 'openai/gpt-6-luna', 'openai/gpt-6-luna:batch', 'openai/gpt-6-sol-pro', 'openai/gpt-6-sol-pro:batch', 'openai/gpt-6-sol', 'openai/gpt-6-sol:batch', 'anthropic/claude-opus-5.5', 'anthropic/claude-opus-5.5:batch', 'xiaomi/mimo-v2.6-pro-ultraspeed', 'xiaomi/mimo-v2.6-flash', 'xiaomi/mimo-v2.6-pro', 'x-ai/grok-4.7', 'x-ai/grok-4.7:batch', 'qwen/qwen3.8-omni-flash', 'prism-ml/ternary-bonsai-2-27b', 'z-ai/glm-5.3-flashx', '~deepseek/deepseek-pro-latest', '~deepseek/deepseek-flash-latest', 'inference-net/schematron-v2-turbo', 'inference-net/schematron-v2-small', '~openai/gpt-astra-latest', '~openai/gpt-sol-latest', '~openai/gpt-terra-latest', '~openai/gpt-luna-latest', 'sakana/fugu-ultra-v2', 'sakana/fugu-max', 'inclusionai/ling-3.0-flash-vl', 'deepseek/deepseek-v4.1-flash', 'deepseek/deepseek-v4.1-flash:batch', 'nex-agi/nex-n2.5-mini', 'nex-agi/nex-n2.5-pro', 'openai/gpt-6-astra', 'openai/gpt-6-astra:batch', 'openai/gpt-6-astra-pro', 'openai/gpt-6-astra-pro:batch', 'inclusionai/ling-3.0-flash-sante', 'qwen/qwen3.8-max-0902', 'qwen/qwen3.8-max-0902:batch', 'meta/muse-spark-1.3-contributor', 'meta/muse-spark-1.3', 'google/gemini-3.8-flash', 'google/gemini-3.8-flash:batch', 'anthropic/claude-fable-5.1', 'anthropic/claude-fable-5.1:batch', 'ibm-granite/granite-4.2-8b', 'tencent/hy4-preview', 'inclusionai/ling-3.0-flash-fin', '~z-ai/glm-flash-latest', 'qwen/qwen3.8-flash', 'z-ai/glm-5.3-flash', 'z-ai/glm-5.3-flash:batch', 'meta/muse-spark-1.2-contributor', 'deepseek/deepseek-v4-flash-vision-exp', 'tencent/hy-mt2-1.8b', 'tencent/hy-mt2-30b-a3b', '~z-ai/glm-latest', 'tencent/hy-mt2-7b', 'z-ai/glm-5.3', 'z-ai/glm-5.3:batch', 'qwen/qwen3.8-27b', 'qwen/qwen3.8-27b:batch', 'dots-studio/dots-3-note-preview:free', 'google/gemini-3.7-flash', 'google/gemini-3.7-flash:batch', 'bytedance-seed/seed-2-1-turbo', 'qwen/qwen3.8-2.4t-a95b', 'deepseek/deepseek-v4-pro-0813', 'x-ai/grok-4.6', 'x-ai/grok-4.6:batch', 'liquid/lfm-2.5-2.6b', 'liquid/lfm-2.5-2.6b:free', 'nvidia/nemotron-3.5-lightning', 'nvidia/nemotron-3.5-lightning:free', 'sakana/sakana-namazu', 'upstage/solar-pro4', 'meta/muse-glimmer-30b', 'meta/muse-glimmer-30b:batch', 'inclusionai/ling-3.0-tiny', 'meta/muse-spark-1.2', '~deepseek/deepseek-v4-flash-latest', 'deepseek/deepseek-v4-flash-0731', 'deepseek/deepseek-v4-flash-0731:batch', 'thinkingmachines/inkling-small', 'thinkingmachines/inkling-small:batch', 'qwen/qwen3.7-flash', 'anthropic/claude-opus-5', 'anthropic/claude-opus-5:batch', 'inclusionai/ling-3.0-flash', 'google/gemini-3.6-flash', 'google/gemini-3.6-flash:batch', 'google/gemini-3.5-flash-lite', 'google/gemini-3.5-flash-lite:batch', 'meituan/longcat-2.0', 'thinkingmachines/inkling', 'moonshotai/kimi-k3', 'moonshotai/kimi-k3:batch', 'meta/muse-spark-1.1', 'openai/gpt-5.6-luna-pro', 'openai/gpt-5.6-luna-pro:batch', 'openai/gpt-5.6-luna', 'openai/gpt-5.6-luna:batch', 'openai/gpt-5.6-terra-pro', 'openai/gpt-5.6-terra-pro:batch', 'openai/gpt-5.6-terra', 'openai/gpt-5.6-terra:batch', 'openai/gpt-5.6-sol-pro', 'openai/gpt-5.6-sol-pro:batch', 'openai/gpt-5.6-sol', 'openai/gpt-5.6-sol:batch', 'x-ai/grok-4.5', '~x-ai/grok-latest', 'aion-labs/aion-3.0-mini', 'aion-labs/aion-3.0', 'tencent/hy3', 'anthropic/claude-sonnet-5', 'anthropic/claude-sonnet-5:batch', 'google/gemini-3.1-flash-lite-image', 'sakana/fugu-ultra', 'google/gemini-3.1-flash-image', 'google/gemini-3-pro-image', 'cohere/north-mini-code:free', 'z-ai/glm-5.2', 'z-ai/glm-5.2:batch', 'moonshotai/kimi-k2.7-code', '~anthropic/claude-fable-latest', 'anthropic/claude-fable-5', 'anthropic/claude-fable-5:batch', 'nvidia/nemotron-3.5-content-safety', 'nvidia/nemotron-3-ultra-550b-a55b', 'nvidia/nemotron-3-ultra-550b-a55b:free', 'qwen/qwen3.7-plus', 'qwen/qwen3.7-plus:batch', 'minimax/minimax-m3', 'minimax/minimax-m3:batch', 'stepfun/step-3.7-flash', 'anthropic/claude-opus-4.8', 'anthropic/claude-opus-4.8:batch', 'qwen/qwen3.7-max', 'x-ai/grok-build-0.1', 'google/gemini-3.5-flash', 'google/gemini-3.5-flash:batch', 'perceptron/perceptron-mk1', 'google/gemini-3.1-flash-lite', 'google/gemini-3.1-flash-lite:batch', 'openai/gpt-chat-latest', 'x-ai/grok-4.3', 'x-ai/grok-4.3:batch', 'mistralai/mistral-medium-3-5', 'mistralai/mistral-medium-3-5:batch', 'nvidia/nemotron-3-nano-omni-30b-a3b-reasoning:free', '~anthropic/claude-haiku-latest', '~openai/gpt-mini-latest', '~google/gemini-pro-latest', '~moonshotai/kimi-latest', '~google/gemini-flash-latest', '~anthropic/claude-sonnet-latest', 'qwen/qwen3.5-plus-20260420', 'qwen/qwen3.6-flash', 'qwen/qwen3.6-35b-a3b', 'qwen/qwen3.6-27b', 'openai/gpt-5.5-pro', 'openai/gpt-5.5-pro:batch', 'openai/gpt-5.5', 'openai/gpt-5.5:batch', 'deepseek/deepseek-v4-pro', 'deepseek/deepseek-v4-flash', 'tencent/hy3-preview', 'xiaomi/mimo-v2.5-pro', 'xiaomi/mimo-v2.5', 'openai/gpt-5.4-image-2', '~anthropic/claude-opus-latest', 'moonshotai/kimi-k2.6', 'anthropic/claude-opus-4.7', 'anthropic/claude-opus-4.7:batch', 'z-ai/glm-5.1', 'google/gemma-4-26b-a4b-it', 'google/gemma-4-26b-a4b-it:free', 'google/gemma-4-31b-it', 'google/gemma-4-31b-it:free', 'qwen/qwen3.6-plus', 'z-ai/glm-5v-turbo', 'x-ai/grok-4.20-multi-agent', 'x-ai/grok-4.20', 'google/lyria-3-pro-preview', 'google/lyria-3-clip-preview', 'rekaai/reka-edge', 'minimax/minimax-m2.7', 'openai/gpt-5.4-nano', 'openai/gpt-5.4-nano:batch', 'openai/gpt-5.4-mini', 'openai/gpt-5.4-mini:batch', 'mistralai/mistral-small-2603', 'z-ai/glm-5-turbo', 'nvidia/nemotron-3-super-120b-a12b', 'bytedance-seed/seed-2.0-lite', 'qwen/qwen3.5-9b', 'openai/gpt-5.4-pro', 'openai/gpt-5.4-pro:batch', 'openai/gpt-5.4', 'openai/gpt-5.4:batch', 'google/gemini-3.1-flash-lite-preview', 'bytedance-seed/seed-2.0-mini', 'google/gemini-3.1-flash-image-preview', 'qwen/qwen3.5-35b-a3b', 'qwen/qwen3.5-27b', 'qwen/qwen3.5-122b-a10b', 'qwen/qwen3.5-flash-02-23', 'google/gemini-3.1-pro-preview-customtools', 'openai/gpt-5.3-codex', 'aion-labs/aion-2.0', 'google/gemini-3.1-pro-preview', 'google/gemini-3.1-pro-preview:batch', 'anthropic/claude-sonnet-4.6', 'anthropic/claude-sonnet-4.6:batch', 'qwen/qwen3.5-plus-02-15', 'qwen/qwen3.5-397b-a17b', 'minimax/minimax-m2.5', 'z-ai/glm-5', 'anthropic/claude-opus-4.6', 'anthropic/claude-opus-4.6:batch', 'qwen/qwen3-coder-next', 'stepfun/step-3.5-flash', 'moonshotai/kimi-k2.5', 'writer/palmyra-x5', 'openai/gpt-audio', 'openai/gpt-audio-mini', 'z-ai/glm-4.7-flash', 'openai/gpt-5.2-codex', 'z-ai/glm-4.7', 'google/gemini-3-flash-preview', 'google/gemini-3-flash-preview:batch', 'nvidia/nemotron-3-nano-30b-a3b', 'openai/gpt-5.2-chat', 'openai/gpt-5.2-pro', 'openai/gpt-5.2-pro:batch', 'openai/gpt-5.2', 'openai/gpt-5.2:batch', 'mistralai/devstral-2512', 'relace/relace-search', 'z-ai/glm-4.6v', 'openai/gpt-5.1-codex-max', 'amazon/nova-2-lite-v1', 'mistralai/ministral-14b-2512', 'mistralai/ministral-8b-2512', 'mistralai/ministral-3b-2512', 'mistralai/mistral-large-2512', 'deepseek/deepseek-v3.2', 'anthropic/claude-opus-4.5', 'anthropic/claude-opus-4.5:batch', 'google/gemini-3-pro-image-preview', 'openai/gpt-5.1', 'openai/gpt-5.1:batch', 'openai/gpt-5.1-codex', 'openai/gpt-5.1-codex-mini', 'moonshotai/kimi-k2-thinking', 'amazon/nova-premier-v1', 'perplexity/sonar-pro-search', 'mistralai/voxtral-small-24b-2507', 'openai/gpt-oss-safeguard-20b', 'openai/gpt-5-image-mini', 'anthropic/claude-haiku-4.5', 'anthropic/claude-haiku-4.5:batch', 'qwen/qwen3-vl-8b-instruct', 'openai/gpt-5-image', 'google/gemini-2.5-flash-image', 'qwen/qwen3-vl-30b-a3b-thinking', 'qwen/qwen3-vl-30b-a3b-instruct', 'openai/gpt-5-pro', 'openai/gpt-5-pro:batch', 'z-ai/glm-4.6', 'anthropic/claude-sonnet-4.5', 'anthropic/claude-sonnet-4.5:batch', 'deepseek/deepseek-v3.2-exp', 'thedrummer/cydonia-24b-v4.1', 'relace/relace-apply-3', 'qwen/qwen3-vl-235b-a22b-instruct', 'deepseek/deepseek-v3.1-terminus', 'qwen/qwen3-coder-flash', 'qwen/qwen3-next-80b-a3b-instruct', 'moonshotai/kimi-k2-0905', 'nousresearch/hermes-4-405b', 'deepseek/deepseek-chat-v3.1', 'mistralai/mistral-medium-3.1', 'z-ai/glm-4.5v', 'openai/gpt-5', 'openai/gpt-5:batch', 'openai/gpt-5-mini', 'openai/gpt-5-mini:batch', 'openai/gpt-5-nano', 'openai/gpt-5-nano:batch', 'openai/gpt-oss-120b', 'openai/gpt-oss-120b:batch', 'openai/gpt-oss-20b', 'openai/gpt-oss-20b:batch', 'anthropic/claude-opus-4.1', 'anthropic/claude-opus-4.1:batch', 'mistralai/codestral-2508', 'qwen/qwen3-coder-30b-a3b-instruct', 'qwen/qwen3-30b-a3b-instruct-2507', 'z-ai/glm-4.5', 'z-ai/glm-4.5-air', 'qwen/qwen3-235b-a22b-thinking-2507', 'qwen/qwen3-coder', 'bytedance/ui-tars-1.5-7b', 'google/gemini-2.5-flash-lite', 'qwen/qwen3-235b-a22b-2507', 'moonshotai/kimi-k2', 'cognitivecomputations/dolphin-mistral-24b-venice-edition', 'tencent/hunyuan-a13b-instruct', 'morph/morph-v3-large', 'morph/morph-v3-large:batch', 'morph/morph-v3-fast', 'morph/morph-v3-fast:batch', 'mistralai/mistral-small-3.2-24b-instruct', 'google/gemini-2.5-flash', 'google/gemini-2.5-pro', 'openai/o3-pro', 'google/gemini-2.5-pro-preview', 'deepseek/deepseek-r1-0528', 'mistralai/mistral-medium-3', 'meta-llama/llama-guard-4-12b', 'qwen/qwen3-30b-a3b', 'qwen/qwen3-14b', 'qwen/qwen3-32b', 'openai/o3', 'openai/o3:batch', 'openai/o4-mini:batch', 'openai/gpt-4.1', 'openai/gpt-4.1:batch', 'openai/gpt-4.1-mini', 'openai/gpt-4.1-mini:batch', 'openai/gpt-4.1-nano', 'openai/gpt-4.1-nano:batch', 'meta-llama/llama-4-maverick', 'meta-llama/llama-4-scout', 'deepseek/deepseek-chat-v3-0324', 'mistralai/mistral-small-3.1-24b-instruct', 'google/gemma-3-4b-it', 'google/gemma-3-12b-it', 'cohere/command-a', 'rekaai/reka-flash-3', 'google/gemma-3-27b-it', 'thedrummer/skyfall-36b-v2', 'perplexity/sonar-reasoning-pro', 'perplexity/sonar-pro', 'perplexity/sonar-deep-research', 'mistralai/mistral-saba', 'aion-labs/aion-rp-llama-3.1-8b', 'qwen/qwen2.5-vl-72b-instruct', 'qwen/qwen-plus', 'openai/o3-mini:batch', 'mistralai/mistral-small-24b-instruct-2501', 'perplexity/sonar', 'microsoft/phi-4', 'deepseek/deepseek-chat', 'cohere/command-r7b-12-2024', 'meta-llama/llama-3.3-70b-instruct', 'amazon/nova-lite-v1', 'amazon/nova-micro-v1', 'amazon/nova-pro-v1', 'openai/gpt-4o-2024-11-20', 'mistralai/mistral-large-2407', 'qwen/qwen-2.5-coder-32b-instruct', 'thedrummer/unslopnemo-12b', 'anthracite-org/magnum-v4-72b', 'meta-llama/llama-3.2-1b-instruct', 'meta-llama/llama-3.2-3b-instruct', 'qwen/qwen-2.5-72b-instruct', 'cohere/command-r-08-2024', 'cohere/command-r-plus-08-2024', 'sao10k/l3.1-euryale-70b', 'sao10k/l3-lunaris-8b', 'openai/gpt-4o-2024-08-06', 'meta-llama/llama-3.1-70b-instruct', 'meta-llama/llama-3.1-8b-instruct', 'mistralai/mistral-nemo', 'openai/gpt-4o-mini', 'openai/gpt-4o-mini-2024-07-18', 'openai/gpt-4o-mini:batch', 'google/gemma-2-27b-it', 'openai/gpt-4o', 'openai/gpt-4o-2024-05-13', 'openai/gpt-4o:batch', 'mistralai/mixtral-8x22b-instruct', 'openai/gpt-4-turbo:batch', 'mistralai/mistral-large', 'openai/gpt-3.5-turbo-0613', 'openai/gpt-3.5-turbo-16k', 'mancer/weaver', 'undi95/remm-slerp-l2-13b', 'gryphe/mythomax-l2-13b', 'openai/gpt-4', 'openrouter/free'})
