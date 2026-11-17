"""Pipeline (STD-0 + throttle v1): preflight -> throttle -> dispatch
-> verify -> gate -> ticket.

Every run writes exactly one ledger row — a complete metered ticket —
including refusals, holds, verification and gate rejections, and
provider errors. An unpriced (unmetered) model stops the run before
any provider call is made.

Throttle v1 wraps the dispatch: the requested model passes the
allowlist/budget resolution (commodity loop classes degrade down
their chain on a budget breach; deliberative classes fail closed),
the call runs under per-model concurrency + backoff with retries,
and every attempt appends one record to the dispatch log — schema
v1.1 (Treasury SLO-TABLE §5.1), the feed Treasury's meter consumes.
"""

import argparse
import os
import queue
import sys
import threading
import time
import uuid
from datetime import datetime, timezone

from . import contracts as contracts_mod
from . import dispatch_log as dispatch_log_mod
from . import envelopes as envelopes_mod
from . import gate as gate_mod
from . import grants as grants_mod
from . import inputs as inputs_mod
from . import lanes
from . import ledger as ledger_mod
from . import livecost as livecost_mod
from . import masking as masking_mod
from . import promotion as promotion_mod
from . import routing as routing_mod

_SUCCESS_RATES_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "docs", "success-rates.json")
from . import throttle as throttle_mod
from . import verify as verify_mod
from .pricing import estimate_cost_usd, price_info

# Provisional clamp for owner-minute accounting (regime NEEDS-SOURCE
# NS-2): shown-to-decision latency above the ceiling counts as the
# ceiling, because latency is not attention. Set from the first two
# metered weeks' timestamp distribution; marked provisional until then.
OWNER_MINUTE_CLAMP = 5.0

RETRYABLE = (ConnectionError, TimeoutError)
ACQUIRE_TIMEOUT_S = 120.0
# Lane-scoped acquire budgets (C-026 defect (ii), the recorded
# alternative shape riding the start-then-acquire fix): cold lanes
# get a longer slot budget than hosted lanes.
ACQUIRE_TIMEOUT_BY_PROVIDER = {"local": 240.0, "gcp": 240.0}
HEDGE_LOSER_GRACE_S = 5.0

# cost_source by provider (schema v1.1 value set: ticks · list ·
# grant-offset · free-tier · local-zero). xAI is special: ticks when
# the response carries the provider's own cost field, else list.
# The GCP lane takes grant-offset when it wires as its own provider.
COST_SOURCE_BY_PROVIDER = {
    "gcp": "grant-offset",   # credit-funded seat; cash cost $0, draw on the connector's ledger line
    "google": "list",        # paid tier since 2026-11-12 19:28 CT (P-024 item 1: the free-tier label misstated the source on a paid key)
    "local": "local-zero",   # own hardware: $0, hardware-bound, no quota
    "groq": "free-tier",     # C-031 free lane (registered, unwired)
    "openrouter": "free-tier",  # C-031 :free set (lane WIRED 2026-11-12 for the catalog-verified rows)
    "sambanova": "free-tier",   # C-031 free lane (registered, unwired)
}

# Per-model overrides (C-023 batch shape flag): the Gemma pair has
# no paid tier — its $0 attempts read free-tier, not the provider's
# list label.
COST_SOURCE_BY_MODEL = {
    "gemma-4-26b-a4b-it": "free-tier",
    "gemma-4-31b-it": "free-tier",
}


def cost_source_for(provider: str, model: str) -> str:
    return COST_SOURCE_BY_MODEL.get(
        model, COST_SOURCE_BY_PROVIDER.get(provider, "list")
    )
TICKS_PER_USD = 10_000_000_000  # xAI: 1 tick = 1e-10 USD

# M-class route enforcement (registry data-policy classes, C-031/C-034):
# providers whose registered rows are all M-class (host may train), and
# the loop classes whose content is sensitive enough to refuse them.
M_CLASS_PROVIDERS = {"openrouter"}
SENSITIVE_LOOP_CLASSES = {"ruling", "commission"}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _iso(ts: float) -> str:
    return datetime.fromtimestamp(ts, timezone.utc).isoformat(timespec="seconds")


def _default_sidecar(ledger_path: str, suffix: str) -> str:
    root, _ext = os.path.splitext(ledger_path)
    return root + suffix


def _attempt_cost(provider: str, model: str, completion) -> tuple[float, str]:
    """(cost_usd, cost_source) for one completed attempt.

    Never raises: an unpriced SERVED model falls back to the
    requested model's rate for the attempt record, and the
    pipeline's served-model check downstream raises the proper
    error:unmetered-served-model stop (a KeyError here would
    masquerade as a provider failure — observed 2026-11-12 when
    gemini-3.5-flash served as gemini-3.6-flash).
    """
    if provider == "xai":
        ticks = (completion.usage or {}).get("cost_in_usd_ticks")
        if ticks is not None:
            return round(int(ticks) / TICKS_PER_USD, 6), "ticks"
    if provider == "openrouter":
        # The provider returns the exact cost in usage.cost — book it
        # exactly, never the token x table estimate (per-prompt $ audit
        # 2026-11-14: booked $0.3392 vs provider $0.6265 because the
        # returned cost was discarded).
        exact = (completion.usage or {}).get("cost")
        if exact is not None:
            return round(float(exact), 6), "provider-cost"
    try:
        cost = estimate_cost_usd(
            provider, completion.model_served or model,
            completion.tokens_in, completion.tokens_out,
        )
    except KeyError:
        cost = estimate_cost_usd(
            provider, model, completion.tokens_in, completion.tokens_out
        )
    return round(cost, 6), cost_source_for(provider, model)


def run(
    prompt: str,
    model: str,
    ledger_path: str = "ledger.jsonl",
    provider: str = "openai",
    envelope: str = "frontier",
    required_terms=(),
    expect_json: bool = False,
    auto_approve: bool = False,
    acknowledge_hold: bool = False,
    transport=None,
    input_fn=input,
    loop_class: str = throttle_mod.DEFAULT_LOOP_CLASS,
    dispatch_log_path: str | None = None,
    throttle_state_path: str | None = None,
    hedge: bool = False,
    hop_count: int = 0,
    seat_confidence: float | None = None,
    seat_contribution: float | None = None,
    seat_mode: str = "chain",
    env: str = "prod",
    profile_version: str | None = None,
    prompt_stamp: dict | None = None,
    input_manifest: dict | None = None,
    routing_class: str | None = None,
    routing_dominant: str | None = None,
    nature: str | None = None,
    assembly_pattern: str | None = None,
    _time_fn=time.time,
    _sleep_fn=time.sleep,
    _monotonic_fn=time.monotonic,
) -> dict:
    lane = lanes.LANE_OF_PROVIDER.get(provider, provider)
    slo_class = throttle_mod.normalize_class(loop_class)
    base = dict(
        prompt=prompt,
        model=model,
        provider=provider,
        envelope=envelope,
        lane=lane,
    )
    dispatch_log_path = dispatch_log_path or _default_sidecar(
        ledger_path, ".dispatch.jsonl"
    )
    state = throttle_mod.ThrottleState(
        throttle_state_path or _default_sidecar(ledger_path, ".throttle.json")
    )
    # The ticket id is minted by the ledger at write time from the
    # line count; peek it now so attempt records can carry loop_id
    # before the ticket exists (same serial-access assumption the
    # ledger itself makes).
    loop_id = ledger_mod._next_ticket_id(ledger_path)
    qkey = dispatch_log_mod.question_key(prompt)
    qshingles = dispatch_log_mod.question_shingles(prompt)
    attempts: list[dict] = []
    if seat_mode not in ("chain", "named"):
        raise ValueError(f"seat_mode must be 'chain' or 'named', got {seat_mode!r}")
    if env not in dispatch_log_mod.ENVS:
        raise ValueError(
            f"env must be one of {dispatch_log_mod.ENVS}, got {env!r}")
    final_extra = {"form_gate_pass": None, "owner_surface_ts": None, "owner_tap_ts": None,
                   "seat_confidence": seat_confidence, "seat_contribution": seat_contribution,
                   "verify_ms": None, "verify_cost_usd": None,
                   "seat_mode": seat_mode, "queue_wait": None,
                   "profile_version": profile_version,
                   # C-039 as adopted by Treasury §5.11: prompt_id +
                   # version + decoding class are feed-resident; the
                   # content hash rides the feed (and pre-registration)
                   # but stays out of the WS-4 dataset.
                   "prompt_stamp": prompt_stamp,
                   # C-047: the input manifest rides beside the
                   # prompt stamp (interim in run records; feed-field
                   # adoption is Treasury's §7 call).
                   "input_manifest": input_manifest,
                   # Promotion path (cluster enablement 2026-11-13):
                   # the pattern a run claims, when it claims one.
                   "assembly_pattern": assembly_pattern,
                   # C-042: the live-cost stamp (set at resolution;
                   # null on records that never resolved).
                   "live_cost": None,
                   # Query Routing Table v0 (ratified 2026-11-14,
                   # deployed 2026-11-15): the routing stamp on routed
                   # runs (table version + hash + class + position);
                   # null on unrouted legacy runs.
                   "routing": None}
    degraded_from: str | None = None
    stall = {"cause": None}

    def finish(row: dict) -> dict:
        status = row["status"]
        if not attempts:
            dispatch_log_mod.append_record(
                dispatch_log_path,
                loop_id=loop_id, loop_class=slo_class,
                seat=row.get("provider", provider), model=row.get("model", model),
                attempt_no=0, ts_dispatch=_iso(_time_fn()), ts_outcome=_iso(_time_fn()),
                latency=0.0, total_tokens=int(row.get("prompt_chars", 0)) // 4,
                band_basis="prompt-estimate",
                outcome="fail", run_outcome=status,
                stall_cause=stall["cause"], hop_count=hop_count,
                env=env,
                question_key=qkey, question_shingles=qshingles,
                **final_extra,
            )
            return row
        for i, att in enumerate(attempts):
            is_final = i == len(attempts) - 1
            outcome = att["outcome"]
            if is_final and outcome == "success" and status not in ("approved",):
                outcome = "partial"  # the call returned; the loop did not approve
            dispatch_log_mod.append_record(
                dispatch_log_path,
                loop_id=loop_id, loop_class=slo_class,
                seat=att["provider"], model=att["model"],
                attempt_no=att["attempt_no"],
                ts_dispatch=att["ts_dispatch"], ts_outcome=att["ts_outcome"],
                latency=att["latency"],
                total_tokens=att["tokens_in"] + att["tokens_out"],
                tokens_in=att["tokens_in"], tokens_out=att["tokens_out"],
                cost_usd=att["cost_usd"], cost_source=att["cost_source"],
                finish_reason=att.get("finish_reason"),
                outcome=outcome,
                degraded_from=degraded_from if i == 0 else None,
                env=env,
                question_key=qkey, question_shingles=qshingles,
                **(final_extra if is_final else {}),
                run_outcome=status if is_final else None,
                stall_cause=stall["cause"] if is_final else None,
                hop_count=hop_count if is_final else None,
            )
        return row

    # M-class data-policy enforcement (C-031 Rule 2, wired 2026-11-12 with
    # the OpenRouter lane): every OpenRouter row is M-class (the host may
    # train on routed content), so sensitive loop classes refuse the
    # route at the gate — a named stop, never a silent degrade. Z-class
    # hosts (Groq/SambaNova per the registry) and self-hosted lanes are
    # unaffected.
    if provider in M_CLASS_PROVIDERS and slo_class in SENSITIVE_LOOP_CLASSES:
        snap = envelopes_mod.preflight(ledger_path, envelope, lane)
        stall["cause"] = "m-class-route"
        return finish(ledger_mod.append_row(
            ledger_path, tokens_in=0, tokens_out=0,
            status="blocked-router:m-class", snapshot=snap,
            checks={"data_policy": (
                f"{provider} rows are M-class; loop_class {slo_class} "
                "is sensitive and refuses M-class routes")}, **base,
        ))

    # Query Routing Table v0 (charter ratified 2026-11-14, docket
    # sections 70/72; deployment act = his directive 2026-11-15): a
    # routed run is admitted or refused HERE, at the chokepoint,
    # before any provider call. TEST-0 binds routed and unrouted runs
    # alike: compartmented material (C-047 sensitivity) fails closed
    # to local lanes only.
    test0 = routing_mod.manifest_is_test0(input_manifest)
    # Compute-nature layering (his ruling 2026-11-16): deterministic
    # work spends zero model tokens BY DEFINITION - a model dispatch
    # stamped deterministic refuses here, routed or not. Algorithmic
    # and probabilistic natures ride the routing stamp as guidance
    # (the nature classifies the workflow; the class table still
    # selects the lane for each step).
    resolved_nature = None
    if nature is not None or routing_class is not None:
        resolved_nature = routing_mod.resolve_nature(
            routing_class or routing_mod.FALLBACK_CLASS, nature)
    if resolved_nature == "deterministic":
        snap = envelopes_mod.preflight(ledger_path, envelope, lane)
        stall["cause"] = "router"
        return finish(ledger_mod.append_row(
            ledger_path, tokens_in=0, tokens_out=0,
            status="blocked-router:nature-deterministic", snapshot=snap,
            checks={"routing": (
                "nature=deterministic spends zero model tokens; "
                "run it as plain compute, not a dispatch")},
            **base,
        ))
    if routing_class is not None:
        decision = routing_mod.resolve(
            routing_class, provider, model,
            dominant=routing_dominant, local_only=test0)
        decision.stamp["nature"] = resolved_nature
        final_extra["routing"] = decision.stamp
        if not decision.allowed:
            snap = envelopes_mod.preflight(ledger_path, envelope, lane)
            stall["cause"] = "router"
            return finish(ledger_mod.append_row(
                ledger_path, tokens_in=0, tokens_out=0,
                status=f"blocked-router:{decision.cause}", snapshot=snap,
                checks={"routing": decision.detail}, **base,
            ))
    elif test0 and provider not in routing_mod.LOCAL_PROVIDERS:
        snap = envelopes_mod.preflight(ledger_path, envelope, lane)
        stall["cause"] = "router"
        return finish(ledger_mod.append_row(
            ledger_path, tokens_in=0, tokens_out=0,
            status="blocked-router:test-0", snapshot=snap,
            checks={"routing": (
                "TEST-0 (compartmented) material fails closed to "
                "local lanes; unrouted frontier request refuses")},
            **base,
        ))

    # Input-side control (E-1, ratified 2026-11-17; I&A Finding
    # F-20): a routed run on a judgment-bearing class must carry a
    # C-047 input manifest — the compartment record of what the
    # judgment is made from. No manifest, or an invalid one,
    # refuses here, before any provider call.
    if routing_class in routing_mod.JUDGMENT_CLASSES:
        if input_manifest is None:
            snap = envelopes_mod.preflight(ledger_path, envelope, lane)
            stall["cause"] = "input"
            return finish(ledger_mod.append_row(
                ledger_path, tokens_in=0, tokens_out=0,
                status="blocked-input:manifest-required", snapshot=snap,
                checks={"input": (
                    f"class {routing_class} is judgment-bearing; a "
                    "C-047 input manifest is required (E-1)")},
                **base,
            ))
        _manifest_errors = inputs_mod.validate_manifest(input_manifest)
        if _manifest_errors:
            snap = envelopes_mod.preflight(ledger_path, envelope, lane)
            stall["cause"] = "input"
            return finish(ledger_mod.append_row(
                ledger_path, tokens_in=0, tokens_out=0,
                status="blocked-input:manifest-invalid", snapshot=snap,
                checks={"input": "; ".join(_manifest_errors)},
                **base,
            ))

    # Promotion path guard (cluster enablement, ratified 2026-11-13):
    # a run claiming a swarm pattern must name a REGISTERED pattern whose
    # eval-gate evidence beat its class baseline, and the class must be a
    # worker floor. Ratification classes refuse mechanically here — the
    # exclusion lives in the dispatch path, not in a comment.
    if assembly_pattern is not None:
        ok, why = promotion_mod.check_pattern(assembly_pattern, slo_class)
        if not ok:
            snap = envelopes_mod.preflight(ledger_path, envelope, lane)
            stall["cause"] = "gate"
            return finish(ledger_mod.append_row(
                ledger_path, tokens_in=0, tokens_out=0,
                status="blocked-promotion", snapshot=snap,
                checks={"promotion": why}, **base,
            ))

    # Gauntlet quarantine guard (C-038): catalog-id rows are measurement
    # only. Named mode is the measurement stratum (Treasury §5.8); any
    # other mode stops by name. They enter no chain, so commodity walks
    # never reach them either.
    if model in throttle_mod.GAUNTLET_IDS and seat_mode != "named":
        snap = envelopes_mod.preflight(ledger_path, envelope, lane)
        stall["cause"] = "quarantine"
        return finish(ledger_mod.append_row(
            ledger_path, tokens_in=0, tokens_out=0,
            status="blocked-router:quarantine", snapshot=snap,
            checks={"containment": (
                "gauntlet rows fire in named (measurement) mode only")},
            **base,
        ))

    # Throttle allowlist first: a banned or unlisted model stops as
    # banned even if it is also unpriced — the ban is the refusal of
    # record (an alias must never dispatch, priced or not).
    try:
        throttle_mod.check_model(model)
    except throttle_mod.BannedModel as exc:
        snap = envelopes_mod.preflight(ledger_path, envelope, lane)
        stall["cause"] = "banned-model"
        return finish(ledger_mod.append_row(
            ledger_path, tokens_in=0, tokens_out=0,
            status="blocked-throttle:banned-model", snapshot=snap,
            checks={"throttle": str(exc)}, **base,
        ))

    # Unmetered dispatch stops the run (STD-0 / ADR-005).
    try:
        price_info(provider, model)
    except KeyError:
        snap = envelopes_mod.preflight(ledger_path, envelope, lane)
        stall["cause"] = "unmetered"
        return finish(ledger_mod.append_row(
            ledger_path, tokens_in=0, tokens_out=0,
            status="blocked-unmetered", snapshot=snap, **base,
        ))

    # Envelope + lane ceilings, read at write time (C-007 section 2).
    snap = envelopes_mod.preflight(ledger_path, envelope, lane)
    if snap["decision"] == "blocked":
        stall["cause"] = "envelope"
        return finish(ledger_mod.append_row(
            ledger_path, tokens_in=0, tokens_out=0,
            status=f"blocked-envelope:{snap['reason']}", snapshot=snap, **base,
        ))
    if snap["decision"] == "hold" and not acknowledge_hold:
        stall["cause"] = "hold"
        return finish(ledger_mod.append_row(
            ledger_path, tokens_in=0, tokens_out=0,
            status="hold-90", snapshot=snap, **base,
        ))

    # C-042 live-cost routing (adopted rule): rank the class's chain
    # by expected cost per successful loop and let the walk follow
    # the ranking. Any failure in the live computation falls back to
    # the static chain — the stamp (built below) carries the mark.
    _rates = livecost_mod.load_success_rates(_SUCCESS_RATES_PATH)
    _chain_order = None
    try:
        _ranked = livecost_mod.rank_candidates(slo_class, prompt, _rates)
        _chain_order = [e["model"] for e in _ranked]
    except Exception:
        _chain_order = None

    # Throttle resolution: error budgets + class behavior.
    try:
        resolution = throttle_mod.resolve(loop_class, model, state, _time_fn(),
                                          seat_mode=seat_mode,
                                          chain_order=_chain_order)
    except throttle_mod.BannedModel as exc:
        stall["cause"] = "banned-model"
        return finish(ledger_mod.append_row(
            ledger_path, tokens_in=0, tokens_out=0,
            status="blocked-throttle:banned-model", snapshot=snap,
            checks={"throttle": str(exc)}, **base,
        ))
    except throttle_mod.BudgetBreached as exc:
        stall["cause"] = "chain-exhausted" if "chain" in str(exc) else "error-budget"
        return finish(ledger_mod.append_row(
            ledger_path, tokens_in=0, tokens_out=0,
            status="blocked-throttle:error-budget", snapshot=snap,
            checks={"throttle": str(exc)}, **base,
        ))
    fire_model = resolution.model
    fire_provider = throttle_mod.MODELS[fire_model].provider
    # C-042: the live-cost stamp for the fired model rides the final
    # + stopped records from here on (run records; feed adoption is
    # Treasury's §7 call). build_stamp never raises — its failure
    # shape IS the PRICING_STALE stamp.
    final_extra["live_cost"] = livecost_mod.build_stamp(
        fire_provider, fire_model, slo_class, prompt, _rates)
    # PII masking seam (Increment 2 wiring; Q-057's condition discharged
    # by the 2026-11-17 retention verification — 16/16 KEEP with the
    # keep-set active, incl. the merged-span split): the register is
    # resolved per run (E-1, ratified 2026-11-17: GD_MASKING_REGISTER,
    # else a masking-register.json at the gate home, else inert with
    # the state stamped on the ticket); when one resolves, the prompt
    # is masked here (after the stamp, before dispatch) and the
    # completion is re-identified before verification. Fail-closed: a
    # register that fails to load, or any mask failure, blocks the
    # ticket. The neural detector binds behind the same seam when the
    # production sidecar lands; the deterministic + register layers
    # are live from this wiring.
    mask_vault = None
    masker = None
    _reg_path = masking_mod.resolve_register_path()
    if _reg_path:
        try:
            masker = masking_mod.Masker(
                masking_mod.Register.load(_reg_path))
            mask_vault = masking_mod.Vault(loop_id)
            prompt = masker.mask(prompt, mask_vault)
            final_extra["masking"] = {
                "active": True, "counts": dict(mask_vault.counts)}
        except masking_mod.MaskingError as exc:
            stall["cause"] = "masking"
            return finish(ledger_mod.append_row(
                ledger_path, tokens_in=0, tokens_out=0,
                status="blocked-masking:register", snapshot=snap,
                checks={"masking": str(exc)}, **base,
            ))
    else:
        # E-1 (ratified 2026-11-17): the seam evaluates on every
        # run and its state lands on the ticket — inert is a
        # recorded state, never a silent absence.
        final_extra["masking"] = {"active": False}
    # Grant-first booking register (his ruling 2026-11-17): loaded
    # before dispatch; a register that cannot be read blocks the
    # ticket — booking correctness is never silently dropped. No
    # register file = the seam is inert. The booking decision itself
    # lands after the run completes (see the grant stamp below).
    grant_register = None
    try:
        grant_register = grants_mod.load_register()
    except grants_mod.GrantError as exc:
        stall["cause"] = "grant-register"
        return finish(ledger_mod.append_row(
            ledger_path, tokens_in=0, tokens_out=0,
            status="blocked-grant:register", snapshot=snap,
            checks={"grant": str(exc)}, **base,
        ))
    # Open-weight seats: the same bench ids serve on 2 seats (local
    # Jarvis · gcp Nightwatch). The run's provider names the seat;
    # the ticket records the seat that actually served.
    if provider in ("local", "gcp") and fire_provider in ("local", "gcp"):
        fire_provider = provider
    degraded_from = resolution.degraded_from
    fire = dict(base, model=fire_model, provider=fire_provider,
                lane=lanes.LANE_OF_PROVIDER.get(fire_provider, fire_provider))
    throttle_checks = {}
    if resolution.note:
        throttle_checks["throttle_note"] = resolution.note
    if resolution.degraded_from:
        throttle_checks.update({
            "throttle_degraded_from": resolution.degraded_from,
            "throttle_chain": resolution.chain,
        })


    completion = None
    last_exc: Exception | None = None
    # Hedged dispatch (Speed Tranche item 2): commodity classes may
    # fire the resolved model and the next chain model in parallel.
    # The first returning completion wins; the loser is cancelled
    # (joined for a short grace, then abandoned — its attempt record
    # reads superseded). Deliberative classes never hedge. V1 picks
    # the first RETURNING completion; verification applies to the
    # winner alone.
    dispatched = False
    if hedge:
        spec = throttle_mod.LOOP_CLASSES[slo_class]
        chain = list(spec.get("chain") or [])
        if spec["behavior"] == "degrade" and fire_model in chain:
            idx = chain.index(fire_model)
            pair_model = None
            for _cand in chain[idx + 1:]:
                if throttle_mod.lane_hold(_cand) is None:
                    pair_model = _cand
                    break
            if pair_model is not None:
                dispatched = True
                throttle_checks["throttle_hedged"] = [fire_model, pair_model]

                def _side(model_id):
                    prov = throttle_mod.MODELS[model_id].provider
                    att = {
                        "attempt_no": 0, "provider": prov, "model": model_id,
                        "ts_dispatch": _iso(_time_fn()), "tokens_in": 0,
                        "tokens_out": 0, "cost_usd": 0.0,
                        "cost_source": cost_source_for(prov, model_id),
                        "outcome": "fail", "latency": 0.0,
                        "ts_outcome": _iso(_time_fn()),
                    }
                    if not state.try_acquire(model_id, _time_fn()):
                        return model_id, None, att, RuntimeError("no slot")
                    t0 = _monotonic_fn()
                    try:
                        comp = lanes.dispatch(prompt, prov, model_id, transport=transport)
                        att["latency"] = _monotonic_fn() - t0
                        att["ts_outcome"] = _iso(_time_fn())
                        att["tokens_in"] = comp.tokens_in
                        att["tokens_out"] = comp.tokens_out
                        att["finish_reason"] = comp.finish_reason
                        att["cost_usd"], att["cost_source"] = _attempt_cost(prov, model_id, comp)
                        att["outcome"] = "success"
                        state.record_success(model_id, _time_fn())
                        return model_id, comp, att, None
                    except Exception as exc2:
                        att["latency"] = _monotonic_fn() - t0
                        att["ts_outcome"] = _iso(_time_fn())
                        state.record_error(model_id, _time_fn())
                        return model_id, None, att, exc2
                    finally:
                        state.release(model_id)

                results: dict[str, tuple] = {}
                done_q: "queue.Queue[str]" = queue.Queue()

                def _run_side(mid):
                    results[mid] = _side(mid)
                    done_q.put(mid)

                threads = []
                for mid in (fire_model, pair_model):
                    th = threading.Thread(target=_run_side, args=(mid,), daemon=True)
                    th.start()
                    threads.append(th)
                settled_order: list[str] = []
                winner_id = None
                deadline = _monotonic_fn() + 660.0
                while _monotonic_fn() < deadline:
                    remaining = [m for m in (fire_model, pair_model) if m not in settled_order]
                    if not remaining:
                        break
                    try:
                        mid = done_q.get(timeout=0.25)
                    except queue.Empty:
                        if winner_id is not None:
                            break  # winner chosen; loser grace elapsed
                        continue
                    settled_order.append(mid)
                    if results[mid][1] is not None and winner_id is None:
                        winner_id = mid
                        # short grace for the loser to settle cheaply
                        grace_end = _monotonic_fn() + HEDGE_LOSER_GRACE_S
                        while _monotonic_fn() < grace_end and len(settled_order) < 2:
                            try:
                                settled_order.append(done_q.get(timeout=0.25))
                            except queue.Empty:
                                pass
                        break
                if winner_id is None and settled_order:
                    winner_id = None  # all settled, none succeeded
                ordered = []
                if winner_id is not None:
                    ordered.append(winner_id)
                ordered += [m for m in settled_order if m != winner_id]
                for n, mid in enumerate(ordered, start=1):
                    _mid, comp2, att2, exc2 = results[mid]
                    att2["attempt_no"] = n
                    if mid != winner_id and att2["outcome"] == "success":
                        att2["outcome"] = "superseded"
                    attempts.append(att2)
                    if mid == winner_id:
                        completion = comp2
                    elif exc2 is not None and last_exc is None:
                        last_exc = exc2
                if winner_id is not None and winner_id != fire_model:
                    wp = throttle_mod.MODELS[winner_id].provider
                    fire = dict(base, model=winner_id, provider=wp,
                                lane=lanes.LANE_OF_PROVIDER.get(wp, wp))
                    fire_model = winner_id
                    fire_provider = wp
                if completion is None and last_exc is None:
                    last_exc = RuntimeError("hedged dispatch: both lanes failed")


    if not dispatched:
        # Dispatch under throttle: concurrency slot, timed attempts,
        # backoff retries on retryable failures; every error feeds the
        # model's error budget. One dispatch record per attempt.
        rule = throttle_mod.MODELS[fire_model]
        completion = None
        last_exc: Exception | None = None
        # C-026 start-then-acquire: a cold lane starts BEFORE the
        # acquire clock runs, so its boot never eats the slot budget
        # that fail-closed classes die on. Live runs only — a caller-
        # supplied transport is already warm by construction.
        if transport is None:
            lanes.warm(fire_provider, fire_model)
        timeout_s = ACQUIRE_TIMEOUT_BY_PROVIDER.get(fire_provider,
                                                    ACQUIRE_TIMEOUT_S)
        # Class-priority queue (C-026 line 1): contended slots grant
        # in class order with aging, not poll order. The waiter
        # registers, and only the queue head may take a slot.
        # The waiter id is unique per run: loop ids repeat across
        # ledgers, and one process can host many runs.
        waiter = f"{loop_id}-{os.getpid()}-{uuid.uuid4().hex[:8]}"
        state.enqueue(fire_model, waiter, loop_class, _time_fn())
        acquired = False
        acquire_start = _monotonic_fn()
        acquire_deadline = acquire_start + timeout_s
        while _monotonic_fn() < acquire_deadline:
            qsnap = state.queue_snapshot(fire_model, _time_fn())
            if not any(e["waiter"] == waiter for e in qsnap):
                # My registration vanished (pruned or raced): re-join.
                state.enqueue(fire_model, waiter, loop_class, _time_fn())
            elif qsnap[0]["waiter"] == waiter and state.try_acquire(
                    fire_model, _time_fn()):
                acquired = True
                break
            _sleep_fn(0.25)
        state.dequeue(fire_model, waiter)
        final_extra["queue_wait"] = round(_monotonic_fn() - acquire_start, 3)
        if not acquired:
            stall["cause"] = "concurrency"
            return finish(ledger_mod.append_row(
                ledger_path, tokens_in=0, tokens_out=0,
                status="blocked-throttle:concurrency", snapshot=snap,
                checks={"throttle": f"{fire_model}: no slot within {timeout_s}s"},
                **fire,
            ))
        try:
            attempt_no = 0
            while True:
                attempt_no += 1
                att = {
                    "attempt_no": attempt_no, "provider": fire_provider,
                    "model": fire_model, "ts_dispatch": _iso(_time_fn()),
                    "tokens_in": 0, "tokens_out": 0,
                    "cost_usd": 0.0,
                    "cost_source": cost_source_for(fire_provider, fire_model),
                    "outcome": "fail",
                }
                started = _monotonic_fn()
                try:
                    completion = lanes.dispatch(
                        prompt, fire_provider, fire_model, transport=transport
                    )
                    att["latency"] = _monotonic_fn() - started
                    att["ts_outcome"] = _iso(_time_fn())
                    att["tokens_in"] = completion.tokens_in
                    att["tokens_out"] = completion.tokens_out
                    att["finish_reason"] = completion.finish_reason
                    att["cost_usd"], att["cost_source"] = _attempt_cost(
                        fire_provider, fire_model, completion
                    )
                    att["outcome"] = "success"
                    attempts.append(att)
                    state.record_success(fire_model, _time_fn())
                    break
                except RETRYABLE as exc:
                    att["latency"] = _monotonic_fn() - started
                    att["ts_outcome"] = _iso(_time_fn())
                    attempts.append(att)
                    last_exc = exc
                    state.record_error(fire_model, _time_fn(),
                                       probation_exempt=(seat_mode == "named"))
                    if attempt_no > rule.max_retries:
                        completion = None
                        break
                    _sleep_fn(throttle_mod.backoff_delay(fire_model, attempt_no - 1))
                except Exception as exc:  # non-retryable: budget still hears it
                    att["latency"] = _monotonic_fn() - started
                    att["ts_outcome"] = _iso(_time_fn())
                    attempts.append(att)
                    state.record_error(fire_model, _time_fn(),
                                       probation_exempt=(seat_mode == "named"))
                    last_exc = exc
                    completion = None
                    break
        finally:
            state.release(fire_model)
    if completion is None:
        exc = last_exc or RuntimeError("dispatch failed")
        stall["cause"] = "provider-error"
        return finish(ledger_mod.append_row(
            ledger_path, tokens_in=0, tokens_out=0,
            status=f"error:{type(exc).__name__}", snapshot=snap,
            checks=throttle_checks, **fire,
        ))

    # The served model must be priced too; alias drift is flagged on
    # the ticket via model_match, and an unpriced served model is an
    # error row, never a silent estimate.
    try:
        price_info(fire_provider, completion.model_served)
    except KeyError:
        stall["cause"] = "unmetered"
        return finish(ledger_mod.append_row(
            ledger_path,
            tokens_in=completion.tokens_in, tokens_out=completion.tokens_out,
            status="error:unmetered-served-model",
            model_served=completion.model_served, snapshot=snap,
            checks=throttle_checks, **fire,
        ))

    if mask_vault is not None:
        completion.text = masker.reidentify(completion.text, mask_vault)
    _v0 = _monotonic_fn()
    result = verify_mod.verify(
        completion.text, required_terms=required_terms, expect_json=expect_json
    )
    final_extra["verify_ms"] = round((_monotonic_fn() - _v0) * 1000.0, 3)
    final_extra["verify_cost_usd"] = 0.0  # the local form gate runs at $0
    final_extra["form_gate_pass"] = bool(result.passed)
    served = dict(model_served=completion.model_served, snapshot=snap)
    checks = dict(result.checks, **throttle_checks)
    # Output contract (H-B2): the return asserts against the
    # served model's declaration; the outcome rides the ticket
    # and the final feed record. PASS-WITH-CAUSE is conformance,
    # never a seat failure (the transcribe exhibits).
    contract_outcome = contracts_mod.assert_contract(
        fire_provider, completion.model_served or fire_model,
        cost_source=attempts[-1]["cost_source"] if attempts else None,
        text=completion.text)
    checks["contract"] = contract_outcome
    final_extra["contract"] = contract_outcome
    # Grant-first booking (his ruling 2026-11-17 10:59 CT): an
    # Anthropic ticket covered by the prepaid credit books
    # grant-offset, never cash. Decided here — after the contract
    # assert reads the pricing basis, before both terminal records
    # write — so the ledger row and the feed's final record carry
    # the booking source. A ticket crossing the boundary books
    # whole-ticket grant-offset with straddle=true (v1 rule).
    if attempts and fire_provider == "anthropic" \
            and attempts[-1]["cost_source"] == "list":
        _grant = grants_mod.decide(
            grant_register, "anthropic", ledger_path,
            sum(att["cost_usd"] for att in attempts))
        if _grant is not None:
            attempts[-1]["cost_source"] = "grant-offset"
            checks["grant"] = dict(_grant)
            final_extra["grant"] = dict(_grant)
    if not result.passed:
        stall["cause"] = "verification"
        return finish(ledger_mod.append_row(
            ledger_path,
            tokens_in=completion.tokens_in, tokens_out=completion.tokens_out,
            status="rejected-verification", checks=checks, **served, **fire,
            cost_override=sum(att["cost_usd"] for att in attempts),
            cost_source=attempts[-1]["cost_source"] if attempts else "",
        ))

    shown_ts = _now()
    started_gate = time.monotonic()
    try:
        approved = gate_mod.approve(
            completion.text, auto_approve=auto_approve, input_fn=input_fn
        )
    except gate_mod.GateRejected:
        approved = False
    decision_ts = _now()
    if not auto_approve:
        final_extra["owner_surface_ts"] = shown_ts
        final_extra["owner_tap_ts"] = decision_ts
    elapsed_min = (time.monotonic() - started_gate) / 60.0
    owner_minutes = 0.0 if auto_approve else min(elapsed_min, OWNER_MINUTE_CLAMP)
    gate_info = {
        "shown": shown_ts,
        "decision": decision_ts,
        "auto": auto_approve,
        "clamp_min": OWNER_MINUTE_CLAMP,
    }
    if not approved:
        stall["cause"] = "gate"
    return finish(ledger_mod.append_row(
        ledger_path,
        tokens_in=completion.tokens_in, tokens_out=completion.tokens_out,
        status="approved" if approved else "rejected-gate",
        checks=checks, owner_minutes=owner_minutes, gate=gate_info,
        **served, **fire,
        cost_override=sum(att["cost_usd"] for att in attempts),
        cost_source=attempts[-1]["cost_source"] if attempts else "",
    ))


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        prog="gated-dispatch",
        description="Dispatch one prompt through verification and an approval gate, metered into a cost ledger (STD-0 ticket).",
    )
    parser.add_argument("prompt", help="the prompt to dispatch")
    parser.add_argument("--model", default="gpt-5-mini")
    parser.add_argument("--provider", default="openai",
                        help="anthropic | google | xai | openai | open")
    parser.add_argument("--envelope", default="frontier",
                        help="frontier | sweeps | open-weight | health | ci-local")
    parser.add_argument("--ledger", default="ledger.jsonl")
    parser.add_argument("--loop-class", default=throttle_mod.DEFAULT_LOOP_CLASS,
                        help="SLO class: panel | commission | ruling (fail-closed) "
                             "| junior | defect | lower-order (degrade); legacy names accepted")
    parser.add_argument("--hedge", action="store_true",
                        help="commodity classes only: fire the resolved model and the next chain model in parallel; first return wins")
    parser.add_argument("--hop-count", type=int, default=0,
                        help="relays before this dispatch (caller-observed; rides the final dispatch record)")
    parser.add_argument("--seat-confidence", type=float, default=None,
                        help="caller-passed per-seat confidence 0..1 (rides the final dispatch record)")
    parser.add_argument("--seat-contribution", type=float, default=None,
                        help="caller-passed per-seat contribution 0..1 (rides the final dispatch record)")
    parser.add_argument("--dispatch-log", default=None,
                        help="dispatch-record JSONL (default: beside the ledger)")
    parser.add_argument("--throttle-state", default=None,
                        help="throttle state JSON (default: beside the ledger)")
    parser.add_argument("--seat-mode", choices=("chain", "named"),
                        default="chain",
                        help="named fires the requested seat as itself (measurement); chain walks the degrade chain")
    parser.add_argument("--env", choices=dispatch_log_mod.ENVS, default="prod",
                        help="lab environment tag on every attempt record (D-BENCH-1 item 1)")
    parser.add_argument("--profile-version", default=None,
                        help="assembly profile version steering this dispatch, where one did (D-BENCH-1 item 4)")
    parser.add_argument("--require-term", action="append", default=[])
    parser.add_argument("--expect-json", action="store_true")
    parser.add_argument("--acknowledge-hold", action="store_true",
                        help="proceed past a 90% hold on the owner's word (recorded)")
    parser.add_argument(
        "--yes",
        action="store_true",
        help="approve without prompting (for approved automation and tests)",
    )
    args = parser.parse_args(argv)
    row = run(
        args.prompt,
        args.model,
        ledger_path=args.ledger,
        provider=args.provider,
        envelope=args.envelope,
        required_terms=args.require_term,
        expect_json=args.expect_json,
        auto_approve=args.yes,
        acknowledge_hold=args.acknowledge_hold,
        loop_class=args.loop_class,
        dispatch_log_path=args.dispatch_log,
        throttle_state_path=args.throttle_state,
        hedge=args.hedge,
        hop_count=args.hop_count,
        seat_confidence=args.seat_confidence,
        seat_contribution=args.seat_contribution,
        seat_mode=args.seat_mode,
        env=args.env,
        profile_version=args.profile_version,
    )
    print(f"{row['ticket']}  {row['status']}  ${row['cost_usd']:.6f}  -> {args.ledger}")
    return 0 if row["status"] == "approved" else 1


if __name__ == "__main__":
    sys.exit(main())
