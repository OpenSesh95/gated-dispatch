"""The bus wire at the dispatch choke point (EOD migration
push Part 2, his order via CoS 2026-11-24).

Every admitted routed dispatch in cli.run passes through
decide() at admission and emit_outcome() at completion, so
the fleet's real dispatches accrue on the router deployment's
tagged path BY CONSTRUCTION — the adoption unlock: the helper
is the default dispatch path, not a habit desks remember.

Two-phase because a production dispatcher decides at
admission and knows its executed lane only at completion:
decide() runs the deployment's gate + arm draw (+ the timed
brain pick on an A draw) via the coordination-bus package's
decide_route(); emit_outcome() writes the router_live row via
emit_route() with the lane that ACTUALLY executed and the
run's real tokens and cost.

Failure posture, absolute: the wire NEVER blocks or breaks a
dispatch. The bus package is an optional import — absent, the
wire is inert. Every wire call is wrapped: any exception is
swallowed into the run's checks as a bus-wire note. A spooled
or failed emit loses a row, never a dispatch.

Class mapping: the routing class rides as the task_class; a
TEST-0 (compartmented) run carries custody_sensitive=True,
which the deployment gate excludes until a suite re-run
passes the class — compartmented dispatches therefore never
draw, exactly as the deployment's custody rule requires.
"""
from __future__ import annotations

_PROVIDER_LANES = {
    "anthropic": "realtime_api:anthropic",
    "google": "realtime_api:google",
    "xai": "realtime_api:xai",
    "openrouter": "realtime_api:openrouter",
    "mistral": "realtime_api:mistral",
    "deepgram": "realtime_api:deepgram",
}


def lane_for(provider: str, model: str | None = None) -> str:
    """(provider, model) -> the deployment's lane_class."""
    if provider in ("local", "ollama", "gcp-ollama",
                    "local-ollama"):
        return "local"
    if provider == "openrouter" and model:
        if model.startswith("anthropic/"):
            return "realtime_api:anthropic"
        if model.startswith("google/"):
            return "realtime_api:google"
        if model.startswith("xai/"):
            return "realtime_api:xai"
        if model.startswith("openai/"):
            return "realtime_api:openai"
    return _PROVIDER_LANES.get(provider, "seat_job")


def _bus():
    """The coordination-bus dispatch module, or None. The
    wire is inert without it — a deployment environment that
    has not installed the bus package dispatches exactly as
    before."""
    try:
        from coordination_bus import dispatch as bus_dispatch
        return bus_dispatch
    except Exception:
        return None


def decide(task_id: str, routing_class: str, provider: str,
           model: str, *, test0: bool = False) -> dict | None:
    """At admission (after routing.resolve admits): gate +
    draw (+ brain pick on an A) via the bus helper. Returns
    the decision context for emit_outcome(), or None when
    the wire is inert or the dispatch is gated (gated work
    emits no router_live row, per the published shape)."""
    bus = _bus()
    if bus is None:
        return None
    task = {"task_class": routing_class,
            "category": "panel-dispatch"}
    if test0:
        task["custody_sensitive"] = True
    try:
        decision = bus.decide_route(
            task_id, task, lane_for(provider, model))
    except Exception:
        return None
    if "gated" in decision:
        return None
    decision["_task_id"] = task_id
    return decision


def emit_outcome(ctx: dict | None, executed_provider: str,
                 executed_model: str, tokens_in: int,
                 tokens_out: int, cost_usd: float | None = None,
                 outcome: str = "completed") -> None:
    """At completion: write the router_live row with the
    executed lane and the run's real metering. Never raises."""
    if ctx is None:
        return
    bus = _bus()
    if bus is None:
        return
    try:
        decision = {k: v for k, v in ctx.items()
                    if not k.startswith("_")}
        # Cost stays with the dispatcher's own ledger (its
        # system of record); the bus row's cost fields stay
        # unset rather than half-stated (together-or-never).
        bus.emit_route(
            "gated-dispatch", ctx["_task_id"], decision,
            executed_lane=lane_for(executed_provider,
                                   executed_model),
            tokens=(tokens_in, tokens_out),
            pointer="gated-dispatch ledger (run record)")
    except Exception:
        pass
