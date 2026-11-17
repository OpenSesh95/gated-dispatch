"""Query Routing Table v0 — live at the STD-0 dispatch chokepoint.

Charter: Query Routing & Feedback System, RATIFIED as drafted (his tap
2026-11-14 17:34 CT; Governance docket section 70). Annex 1 RATIFIED
WHOLE (his tap 2026-11-14 17:58 CT; docket section 72). Deployment act:
his directive 2026-11-15 09:21 CT (fast-track, AD HOC class under the
bifurcation). Table home of record:
~/workspace/research-team/prompt-layer/ROUTING-TABLE.md — this module is
the gate's executable copy; the class block is cited by hash, never
re-derived here.

Rules enforced at the chokepoint (cli.run):
- A routed run names its class. The class admits a chain (cheapest
  capable first) plus, where the row says so, one flagship. A requested
  (provider, model) outside the admitted set stops by name:
  blocked-router:class-mismatch. Local-estate models are admitted on
  every class (Geneva's own lanes are always the cheapest capable).
- Geneva-direct classes (qr-quick-lookup, qr-life-ops, qr-career-ops)
  admit no frontier dispatch; a frontier request under one stops as
  blocked-router:geneva-direct.
- TEST-0 (charter local-only rule): an input manifest whose data
  sensitivity is "compartmented" (C-047 vocabulary) fails closed to
  local lanes only, routed or not. A frontier request stops as
  blocked-router:test-0. No degrade, no substitution.
- B7 latency bypass (Annex 1 B7): the ad hoc class bypasses
  classification entirely, Geneva-direct. routing_class="ad-hoc" on a
  frontier request stops as blocked-router:b7-bypass; on a local
  request it proceeds stamped as the bypass class.
- qr-combination is a composition rule, not a lane: it resolves through
  its dominant class (routing_dominant). Without a dominant it stops as
  blocked-router:combination-needs-dominant.
- An unknown class id falls back to qr-quick-lookup, logged
  unclassified in the stamp (table face rule).
- Masking seam: the PII masker (gated_dispatch.masking, ratified
  2026-11-15) binds at this same chokepoint in its own wiring PR,
  sequenced behind its retention verification. Routing does not depend
  on it and it does not depend on routing; neither blocks the other.

The stamp (integration binding, gate desk filing 2026-11-14): a routed
run's final feed record carries routing = {table_version, table_hash,
class, lane, position, unclassified, interim, composed_from}.

Table v0.1 (2026-11-17, his routing-spread directive 11:13 CT, deploy
lane): chains re-pointed so Claude is no longer the default where
another lane fits the task class. OpenRouter's proven free seats enter
chains for the first time (north-mini-code heads qr-coding-burst;
nemotron-3-ultra joins qr-panel-verdict and qr-research). Gemini
heads the drafting chains (canon-drafting, content-voice) with the
Claude flagship kept at the judgment point. qr-commission-ruling is
unchanged (the fork is charter, not a deploy gap) and
qr-spiritual-study is unchanged (gold-source discipline defines the
lane). Class block + hash updated at the table home in the same act.
"""

from dataclasses import dataclass, field

TABLE_VERSION = "v0.1"
TABLE_HASH = "4ac7f8f70c628d102e17abdbe072f1469a142375e00dd296c911d9ee0adb628b"

LOCAL_PROVIDERS = frozenset({"local", "gcp"})
BYPASS_CLASS = "ad-hoc"

# Judgment-bearing classes (E-1, ratified 2026-11-17, audit packet
# item E-1 / I&A Finding F-20): the classes whose outputs ARE
# judgments — a ruling, a verdict. A routed run on one of these
# classes must carry a C-047 input manifest (cli.run refuses
# without one, fail-closed): the input-side control that engages
# by default at the seam. Widening this set is a supersede act on
# the record, not a caller choice.
JUDGMENT_CLASSES = frozenset({"qr-commission-ruling",
                              "qr-panel-verdict"})
FALLBACK_CLASS = "qr-quick-lookup"

# Compute-nature layering (his ruling 2026-11-16, Architecture Map):
# every task/action/workflow classifies by the nature of its
# computation, and the nature rides the stamps beside the class.
#   deterministic - rules/scripts; zero model tokens; plain compute.
#   algorithmic   - fixed control flow, model steps inside, outputs
#                   verified deterministically; open-weight lanes.
#   probabilistic - open-ended judgment; frontier tokens at judgment
#                   points only.
# The nature classifies the WORKFLOW, not each step (a panel is
# algorithmic as a workflow though its seats judge). Class defaults
# below are starting points; the stamper classifies on-touch and may
# override per piece.
NATURES = ("deterministic", "algorithmic", "probabilistic")
CLASS_NATURE = {
    "qr-quick-lookup": "algorithmic",
    "qr-life-ops": "deterministic",
    "qr-career-ops": "deterministic",
    "qr-live-wire": "probabilistic",
    "qr-research": "probabilistic",
    "qr-spiritual-study": "probabilistic",
    "qr-canon-drafting": "probabilistic",
    "qr-content-voice": "probabilistic",
    "qr-coding-burst": "algorithmic",
    "qr-commission-ruling": "probabilistic",
    "qr-panel-verdict": "algorithmic",
    "qr-combination": "probabilistic",
    "ad-hoc": "deterministic",
    "human-act": "deterministic",
}
_LANE_HINT = {
    "deterministic": "none (plain compute, zero tokens)",
    "algorithmic": "open-weight first (local / gcp / open lanes)",
    "probabilistic": "frontier at judgment points only",
}
DEFAULT_WEIGHT = {"impact": "medium", "deliverables": 1}


def resolve_nature(class_id: str, nature: str | None = None) -> str:
    """The nature for a stamp: the stamper's on-touch call wins; the
    class default is the fallback; an unknown nature raises."""
    if nature is not None:
        if nature not in NATURES:
            raise ValueError("unknown nature: %r" % (nature,))
        return nature
    return CLASS_NATURE.get(class_id, "probabilistic")


def nature_lane_hint(nature: str) -> str:
    """Nature -> lane mapping (cheapest capable first), carried on
    the stamp as guidance. The one hard rule lives in cli.run:
    deterministic work never reaches a model dispatch."""
    return _LANE_HINT[nature]


@dataclass(frozen=True)
class ClassSpec:
    class_id: str
    lane: str
    chain: tuple = ()          # ((provider, model), ...) cheapest first
    flagship: tuple | None = None
    geneva_direct: bool = False
    interim: bool = False


CLASSES = {
    "qr-quick-lookup": ClassSpec(
        "qr-quick-lookup", "Geneva-direct", geneva_direct=True),
    "qr-life-ops": ClassSpec(
        "qr-life-ops", "Geneva-direct", geneva_direct=True),
    "qr-career-ops": ClassSpec(
        "qr-career-ops", "Geneva-direct + desks", geneva_direct=True),
    "qr-live-wire": ClassSpec(
        "qr-live-wire", "Grok wire",
        chain=(("xai", "grok-4.20-0309-non-reasoning"),),
        flagship=("xai", "grok-4.20-multi-agent-0309")),
    "qr-research": ClassSpec(
        "qr-research", "Gemini library + OpenRouter seat + Research Team",
        chain=(("google", "gemini-3.6-flash"),
               ("openrouter", "nemotron-3-ultra")),
        flagship=("google", "gemini-4-argon")),
    "qr-spiritual-study": ClassSpec(
        "qr-spiritual-study", "Library lane, gold source first",
        chain=(("google", "gemini-3.6-flash"),),
        flagship=("google", "gemini-4-argon")),
    "qr-canon-drafting": ClassSpec(
        "qr-canon-drafting", "Gemini draft + Claude architect",
        chain=(("google", "gemini-3.6-flash"),
               ("google", "gemini-4-argon"),
               ("anthropic", "claude-sonnet-5-5")),
        flagship=("anthropic", "claude-opus-5-5")),
    "qr-content-voice": ClassSpec(
        "qr-content-voice", "Multi-lane cluster via studios + voice profile",
        chain=(("google", "gemini-3.6-flash"),
               ("xai", "grok-4.20-0309-non-reasoning"),
               ("anthropic", "claude-haiku-5-5"),
               ("anthropic", "claude-sonnet-5-5")),
        flagship=("anthropic", "claude-opus-5-5")),
    "qr-coding-burst": ClassSpec(
        "qr-coding-burst", "Open-weight first - INTERIM (Courier gap)",
        chain=(("openrouter", "north-mini-code"),
               ("google", "gemini-3.6-flash"),
               ("anthropic", "claude-sonnet-5-5")),
        flagship=("anthropic", "claude-opus-5-5"),
        interim=True),
    "qr-commission-ruling": ClassSpec(
        "qr-commission-ruling", "Fork (Geneva + unprimed Opus)",
        chain=(),
        flagship=("anthropic", "claude-opus-5-5")),
    "qr-panel-verdict": ClassSpec(
        "qr-panel-verdict", "Panel via STD-0 gated dispatch",
        chain=(("google", "gemini-3.6-flash"),
               ("openrouter", "nemotron-3-ultra"),
               ("xai", "grok-4.20-0309-non-reasoning"),
               ("anthropic", "claude-haiku-5-5")),
        flagship=("anthropic", "claude-opus-5-5")),
    "qr-combination": ClassSpec(
        "qr-combination", "COMBINATION RULE (dominant class lane)"),
}


@dataclass
class Decision:
    allowed: bool
    stamp: dict = field(default_factory=dict)
    cause: str | None = None     # blocked-router:<cause> suffix
    detail: str = ""


def _base_stamp(spec: ClassSpec, unclassified=False, composed_from=None):
    return {
        "table_version": TABLE_VERSION,
        "table_hash": TABLE_HASH,
        "class": spec.class_id,
        "lane": spec.lane,
        "position": None,
        "unclassified": unclassified,
        "interim": spec.interim,
        "composed_from": composed_from,
    }


def is_local(provider: str) -> bool:
    return provider in LOCAL_PROVIDERS


def _resolved_spec(class_id: str, dominant: str | None):
    """(spec, composed_from) with fallback + combination resolution."""
    spec = CLASSES.get(class_id) or CLASSES[FALLBACK_CLASS]
    composed_from = None
    if spec.class_id == "qr-combination" and dominant in CLASSES \
            and dominant != "qr-combination":
        composed_from = "qr-combination"
        spec = CLASSES[dominant]
    return spec, composed_from


def job_stamp(class_id: str, dominant: str | None = None,
              nature: str | None = None, weight: dict | None = None) -> dict:
    """The lane stamp a scheduled job carries (Router x Orchestration,
    his directive 2026-11-15): the job declares its routing class at
    definition time, and any model work it fires goes through the gate
    under that class instead of calling a model directly.

    selected = the lane target the class resolves to today: the chain
    head for frontier classes, the flagship for flagship-only classes,
    "geneva-direct" for Geneva-direct classes.
    """
    spec, composed_from = _resolved_spec(class_id, dominant)
    if spec.geneva_direct:
        selected = "geneva-direct"
    elif spec.chain:
        selected = f"{spec.chain[0][0]}/{spec.chain[0][1]}"
    elif spec.flagship is not None:
        selected = f"{spec.flagship[0]}/{spec.flagship[1]} (flagship)"
    else:
        selected = "geneva-direct"
    nat = resolve_nature(spec.class_id, nature)
    return {
        "routing_class": spec.class_id,
        "routing_dominant": dominant if composed_from else None,
        "table_version": TABLE_VERSION,
        "table_hash": TABLE_HASH,
        "lane": spec.lane,
        "selected": selected,
        "composed_from": composed_from,
        "nature": nat,
        "weight": dict(weight) if weight else dict(DEFAULT_WEIGHT),
        "lane_hint": nature_lane_hint(nat),
    }


def decomposition_stamp(class_id: str, dominant: str | None = None,
                        nature: str | None = None,
                        weight: dict | None = None) -> dict:
    """The stamp a task record carries AT DECOMPOSITION TIME (Router x
    Decomposition, his directive 2026-11-15): lane choice is made where
    the work is shaped, not at dispatch. These fields ride the ticket /
    task record; the dispatch that later executes the piece passes
    routing_class (and routing_dominant) to cli.run unchanged.
    """
    spec, composed_from = _resolved_spec(class_id, dominant)
    nat = resolve_nature(spec.class_id, nature)
    return {
        "routing_class": spec.class_id,
        "routing_dominant": dominant if composed_from else None,
        "table_version": TABLE_VERSION,
        "lane": spec.lane,
        "composed_from": composed_from,
        "nature": nat,
        "weight": dict(weight) if weight else dict(DEFAULT_WEIGHT),
        "lane_hint": nature_lane_hint(nat),
    }


def manifest_is_test0(input_manifest) -> bool:
    """TEST-0 = C-047 sensitivity 'compartmented' (charter local-only)."""
    if not input_manifest:
        return False
    data = input_manifest.get("data") or {}
    return str(data.get("sensitivity", "")).lower() == "compartmented"


def select(class_id: str, dominant: str | None = None):
    """The chain head for a class: (provider, model) cheapest capable.

    Returns None for Geneva-direct classes and for flagship-only
    classes (commission-ruling selects its flagship explicitly).
    """
    spec = CLASSES.get(class_id)
    if spec is None:
        spec = CLASSES[FALLBACK_CLASS]
    if class_id == "qr-combination" and dominant in CLASSES:
        return select(dominant)
    if spec.chain:
        return spec.chain[0]
    return None


def resolve(class_id: str, provider: str, model: str,
            dominant: str | None = None,
            local_only: bool = False) -> Decision:
    """Admit or refuse one routed dispatch request."""
    # B7 latency bypass: the ad hoc class never classifies; it is
    # Geneva-direct by definition. A frontier request under it is a
    # contradiction and stops by name.
    if class_id == BYPASS_CLASS:
        stamp = {
            "table_version": TABLE_VERSION, "table_hash": TABLE_HASH,
            "class": "b7-bypass", "lane": "Geneva-direct",
            "position": "bypass", "unclassified": False,
            "interim": False, "composed_from": None,
        }
        if local_only and not is_local(provider):
            return Decision(False, stamp, "test-0",
                            "TEST-0 material fails closed to local lanes")
        if not is_local(provider):
            return Decision(
                False, stamp, "b7-bypass",
                "ad hoc class is Geneva-direct (B7 bypass); "
                f"frontier request {provider}/{model} refuses")
        return Decision(True, stamp)

    unclassified = class_id not in CLASSES
    spec = CLASSES.get(class_id) or CLASSES[FALLBACK_CLASS]
    composed_from = None
    if spec.class_id == "qr-combination":
        if dominant not in CLASSES or dominant == "qr-combination":
            stamp = _base_stamp(spec, unclassified)
            return Decision(
                False, stamp, "combination-needs-dominant",
                "qr-combination resolves through a dominant class; "
                "none named")
        composed_from = spec.class_id
        spec = CLASSES[dominant]

    stamp = _base_stamp(spec, unclassified, composed_from)

    if local_only and not is_local(provider):
        return Decision(
            False, stamp, "test-0",
            "TEST-0 (compartmented) material fails closed to local "
            f"lanes; frontier request {provider}/{model} refuses")

    if is_local(provider):
        stamp["position"] = "local"
        return Decision(True, stamp)

    if spec.geneva_direct:
        return Decision(
            False, stamp, "geneva-direct",
            f"class {spec.class_id} is Geneva-direct; frontier "
            f"request {provider}/{model} refuses")

    pair = (provider, model)
    if pair in spec.chain:
        stamp["position"] = f"chain-{spec.chain.index(pair)}"
        return Decision(True, stamp)
    if spec.flagship is not None and pair == spec.flagship:
        stamp["position"] = "flagship"
        return Decision(True, stamp)
    admitted = [f"{p}/{m}" for p, m in spec.chain]
    if spec.flagship is not None:
        admitted.append(f"{spec.flagship[0]}/{spec.flagship[1]} (flagship)")
    return Decision(
        False, stamp, "class-mismatch",
        f"class {spec.class_id} admits [{'; '.join(admitted)}]; "
        f"requested {provider}/{model} refuses")
