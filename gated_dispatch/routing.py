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

Table v0.2 (2026-11-17, Reliability commission AR-20261117-06):
qr-draft-check added — the outward-draft compliance check on its
designated checker seat (anthropic/claude-opus-5-5, chain of one: no
spread, no degrade; a substituted checker is a different gate).
Verdicts only; the checker never drafts. JUDGMENT_CLASSES is NOT
widened by this row (a supersede question, named at the table home).

Table v0.3 (2026-11-17, his direct commission 23:22 CT — five-lane
router): the compute-nature taxonomy extends from three lanes to
five — deterministic · algorithmic · statistical · reasoning ·
probabilistic — and gains the MODEL BINDING table (MODEL_BINDINGS
below): nature/modality -> designated models, bound ONLY where a
smoke proof exists (binding source: FinOps' capability map
2026-11-17). LIST-ONLY models are scenery and stay unbound; the two
seeded exceptions carry their proof class on their face. The
priming wrap rides this version in cli.run: a routed service
dispatch on an external lane must carry a C-039 prompt stamp whose
entries verify against the catalogue — no unprimed external
dispatch.

Table v0.4 (2026-11-17, gate v0.4.37): the binding table is
RECONCILED to FinOps' deployment annex (the map's MODEL→LANE
assignment form, filed the same night) — see the binding-table
comment for the deltas. v0.3 stood on dev only and was never
certified; v0.4 supersedes it before any cert packet.

Table v0.5 (2026-11-18, gate v0.4.38): ONE amendment by his direct
word (00:50 CT) — gemini-3.1-flash-lite is RE-BOUND under
statistical as a seeded exception over the annex's scenery class,
its class and the thinking-budget warning on the binding's face.
Rides the same cert packet as v0.4.

Table v0.6 (2026-11-18, gate v0.4.40): the statistical EMBEDDING
seat binds — gemini-embedding-001, designated, on FinOps' proof
(a single embedContent call, 3072-dimension vector, < $0.001).
The annex's named embeddings gap closes. Rides the v0.4.39 patch
cert packet as its second item.

Table v0.7 (2026-11-18, gate v0.4.41): qr-draft-check RE-BINDS,
Shape B (his ruling 01:22 CT) — the checker chain AND the
flagship seat move from claude-opus-5-5 to
grok-4.20-0309-reasoning, on FinOps' frontier-proof (draft-check
91.89 = Opus exactly, 0 form fails, ~1/7 the leg cost). The gate
desk's Shape A read (flagship stays Opus as the appeal court) is
recorded as dissent in the CHANGELOG; his call stands. Rides the
patch cert packet as its third item.
"""

from dataclasses import dataclass, field

from . import throttle as throttle_mod

TABLE_VERSION = "v0.8"
TABLE_HASH = "37625b47c0a56ccc58c8bc7ef19ebf33a53ff901396cd1f8fa7016a5f027dbf4"

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

# Compute-nature layering (his ruling 2026-11-16, Architecture Map;
# extended to five lanes by his direct commission 2026-11-17 23:22
# CT): every task/action/workflow classifies by the nature of its
# computation, and the nature rides the stamps beside the class.
#   deterministic - rules/scripts; zero model tokens; plain compute.
#     Dispatch REFUSED at the chokepoint (standing rule).
#   algorithmic   - fixed control flow, model steps inside, outputs
#     verified deterministically; code/local-first.
#   statistical   - fast/small-model work: classification, vision,
#     transcription, triage — priced per task, verified cheap.
#   reasoning     - mid-tier reasoning models; frontier tokens only
#     on escalation to probabilistic.
#   probabilistic - open-ended judgment; frontier tokens at judgment
#     points only.
# The nature classifies the WORKFLOW, not each step (a panel is
# algorithmic as a workflow though its seats judge). Class defaults
# below are starting points; the stamper classifies on-touch and may
# override per piece.
NATURES = ("deterministic", "algorithmic", "statistical",
           "reasoning", "probabilistic")
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
    "qr-draft-check": "probabilistic",
    "qr-commission-ruling": "probabilistic",
    "qr-panel-verdict": "algorithmic",
    "qr-combination": "probabilistic",
    "ad-hoc": "deterministic",
    "human-act": "deterministic",
}
_LANE_HINT = {
    "deterministic": "none (plain compute, zero tokens)",
    "algorithmic": "open-weight first (local / gcp / open lanes)",
    "statistical": "bound small/fast seats (MODEL_BINDINGS); priced per task",
    "reasoning": "bound reasoning seats (MODEL_BINDINGS); frontier on escalation only",
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


# ---------------------------------------------------------------------
# Model binding table (table v0.3; his direct commission 2026-11-17
# 23:22 CT). Binding source: FinOps' capability map 2026-11-17 and
# its deployment annex (MODEL→LANE assignments, filed the same
# night) — a model binds ONLY on a smoke proof; LIST-ONLY models
# are scenery and stay unbound. RECONCILED at v0.4 (2026-11-17,
# gate v0.4.37) to the annex's assignments: the local trio binds
# under algorithmic; deepseek + grok bind under reasoning; the
# image-gen + tts rows fold under probabilistic + statistical per
# the annex; gemini-3.1-flash-lite and grok-4.20-0309-reasoning are
# UNBOUND (the annex classes both scenery — only the non-reasoning
# Grok variant was smoked, and flash-lite text is cataloged only).
# Two tiers: DISPATCHABLE = the gate's text seam can serve the seat
# today (registered + priced); DESIGNATED = the router's designated
# model for a modality the text seam does not serve (audio, image)
# — callers use the named lane's own endpoint; the binding is the
# designation of record, not a dispatch promise. Proof strings cite
# the map/annex.


@dataclass(frozen=True)
class Binding:
    provider: str
    model: str
    modality: str
    tier: str
    proof: str
    note: str = ""


MODEL_BINDINGS: dict[str, tuple[Binding, ...]] = {
    # Dispatch of deterministic work is refused at the chokepoint —
    # no model binds, by rule (annex: code only, $0 tokens).
    "deterministic": (),
    # Algorithmic (code/local-first): the Draw-1-proven local trio
    # (annex assignments; $0 cash, duty-priced under the GPU-hour
    # envelope).
    "algorithmic": (
        Binding("local", "qwen3:14b", "local workhorse legs",
                "dispatchable",
                "PROVEN — Draw 1 baselines 2026-11-15: field-acc 0.990 (annex)"),
        Binding("local", "deepseek-r1:14b", "local reasoning legs",
                "dispatchable",
                "PROVEN — Draw 1: field-acc 0.285 (annex)",
                "bind only where its measured shape fits (annex)"),
        Binding("local", "llama3.1:8b", "local legs", "dispatchable",
                "PROVEN — Draw 1: 0.000 field-acc as a FORM failure (fences vs the JSON-only instruction), probe-verified (annex)",
                "bind only behind a form gate (annex)"),
    ),
    "statistical": (
        Binding("openrouter", "mistralai/voxtral-small-24b-2507",
                "speech-to-text (primary)", "designated",
                "PROVEN — capability map: transcript exact ($0.0003037 per 3.4s clip TICKS, ~$0.0054/min)",
                "audio seam — not served through the text seam"),
        Binding("google", "gemini-3.5-transcribe",
                "speech-to-text (alternate)", "designated",
                "PROVEN — capability map: near-exact, dedicated audioTranscription output",
                "audio seam — not served through the text seam"),
        Binding("openrouter", "tencent/hy4-flash",
                "vision tagging (primary)", "dispatchable",
                "PROVEN — capability map: red-square vision test exact; cheapest vision in the three realms ($0.035/$0.14 LIST)"),
        Binding("google", "gemini-3.8-flash-lite-tts",
                "text-to-speech", "designated",
                "PROVEN — capability map: 33 chars -> 3.36s speech (voice Kore), token counts verified",
                "the estate's ONLY voice — single-source gap named in the annex"),
        Binding("google", "gemini-embedding-001", "embeddings",
                "designated",
                "PROVEN — FinOps proof 2026-11-18: a single embedContent call returned a 3072-dimension vector, cost < $0.001",
                "the statistical lane's embedding seat — the annex's named gap, closed by this proof. Not served through the text seam; callers use the Gemini embedContent endpoint"),
        Binding("google", "gemini-3.1-flash-lite", "text/triage",
                "dispatchable",
                "SEEDED EXCEPTION — re-bound by his direct word 2026-11-18 00:50 CT over the annex's scenery class (cataloged only; the lane is proven via gemini-3.5-flash)",
                "THINKING BUDGET REQUIRED (the map's verified warning): Gemini flash models burn thought tokens by default and starve small output budgets — set the budget explicitly; the transport parameter is a named follow-up"),
        Binding("google", "gemini-3.5-flash",
                "vision tagging (alternate)", "dispatchable",
                "PROVEN — capability map: vision test exact (1,089 image tokens per small PNG, verified)",
                "gate REPINS 3.5->3.6 at dispatch (canary drift 0093): the served seat is 3.6 until the repin is revisited on canary evidence"),
    ),
    "reasoning": (
        Binding("openrouter", "deepseek/deepseek-v4.1-flash-1017",
                "triage / routing / gate-adjacent (primary)",
                "dispatchable",
                "PROVEN — capability map: ran live; price-watch verified 2026-11-17 ($0.036/$0.50)",
                "reasoning-first: max_tokens must cover reasoning before content. GAUNTLET-CONTAINED at this version (named-mode only, its registration class); chain seating rides a gauntlet-exit act — the map's run is the first exit evidence"),
        Binding("openrouter", "tencent/hy4-flash",
                "cheap reasoning (secondary)", "dispatchable",
                "PROVEN — capability map (vision exact; also the statistical vision primary)"),
        Binding("xai", "grok-4.20-0309-non-reasoning",
                "workhorse + vision", "dispatchable",
                "PROVEN — capability map: text + vision exact ($0.00018/call TICKS; LIST $1.25/$2.50)"),
        Binding("google", "gemini-3.5-flash",
                "workhorse drafting", "dispatchable",
                "PROVEN — capability map: text exact",
                "THINKING CAVEAT (annex, verified): 82-307 thought tokens on trivial prompts — set budgets explicitly or the lane bills reasoning on every call. Gate REPINS 3.5->3.6 at dispatch (drift 0093)"),
    ),
    "probabilistic": (
        Binding("anthropic", "claude-opus-5-5", "text/judgment",
                "dispatchable",
                "Unchanged — the standing judgment seat (the annex: frontier judgment seats bind under the existing table, unchanged)"),
        Binding("openrouter", "openai/gpt-5.5",
                "text/judgment (flagship voice)", "dispatchable",
                "PROVEN — BYOK smoke + bake-off 2026-11-19: 27 dispatches through the gate, $0 ticketed (BYOK carried them)",
                "MASKING CONDITION (his order 2026-11-19, fail-closed): briefs are masked before this seat is dispatched; Leela-private material never goes; an unattested judgment dispatch refuses at the gate (blocked-masking:openai-seat); a brief that cannot be masked without gutting it means the seat sits the panel out. BATCH BAR: the seat rides OpenRouter (30-day batch retention) — its legs never batch under the provenance bar"),
        Binding("xai", "grok-imagine-image",
                "image generation (primary)", "designated",
                "PROVEN — capability map: image returned, $0.0200/image TICKS exact",
                "per-image pricing (no token row); xAI images endpoint; b64_json only under ZDR"),
        Binding("google", "gemini-3.1-flash-lite-image",
                "image generation (alternate)", "designated",
                "PROVEN — capability map: 390 KB JPEG returned, 1,120 image tokens/image verified",
                "image-token pricing; not served through the text seam"),
    ),
}


def bindings_for(key: str) -> tuple[Binding, ...]:
    """The binding rows for a nature or modality key. Unknown keys
    raise — an unbound lane is a stated fact (empty tuple on a known
    key), never a silent guess."""
    if key not in MODEL_BINDINGS:
        raise ValueError(f"unknown binding key {key!r}")
    return MODEL_BINDINGS[key]


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
    # Additional admitted flagship VOICES (v0.8): a convener may name
    # one explicitly and it dispatches as a voice alongside the
    # standing seats. The default flagship selection never changes —
    # a voice fires only when named.
    flagship_voices: tuple = ()
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
    "qr-draft-check": ClassSpec(
        "qr-draft-check", "xAI Grok reasoning seat (designated checker)",
        chain=(("xai", "grok-4.20-0309-reasoning"),),
        flagship=("xai", "grok-4.20-0309-reasoning")),
    "qr-commission-ruling": ClassSpec(
        "qr-commission-ruling", "Fork (Geneva + unprimed Opus)",
        chain=(),
        flagship=("anthropic", "claude-opus-5-5"),
        flagship_voices=(("openrouter", "openai/gpt-5.5"),)),
    "qr-panel-verdict": ClassSpec(
        "qr-panel-verdict", "Panel via STD-0 gated dispatch",
        chain=(("google", "gemini-3.6-flash"),
               ("openrouter", "nemotron-3-ultra"),
               ("xai", "grok-4.20-0309-non-reasoning"),
               ("anthropic", "claude-haiku-5-5")),
        flagship=("anthropic", "claude-opus-5-5"),
        flagship_voices=(("openrouter", "openai/gpt-5.5"),)),
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

    # Seat re-pins (throttle.REPINS — canary-drift re-pins, C-023
    # R-1): dispatch fires the EFFECTIVE seat, so admission judges
    # the effective seat. A request naming the drifted id of a class
    # seat is admitted at the seat's position, with the re-pin named
    # on the stamp. (Found by the 2026-11-18 E2E sweep: the annex-
    # bound gemini-3.5-flash refused every routed class because the
    # chains carry its re-pin, gemini-3.6-flash.)
    effective = throttle_mod.REPINS.get(model, model)
    if effective != model:
        stamp["repinned_from"] = model
    pair = (provider, effective)
    if pair in spec.chain:
        stamp["position"] = f"chain-{spec.chain.index(pair)}"
        return Decision(True, stamp)
    if spec.flagship is not None and pair == spec.flagship:
        stamp["position"] = "flagship"
        return Decision(True, stamp)
    if pair in spec.flagship_voices:
        stamp["position"] = "flagship-voice"
        return Decision(True, stamp)
    admitted = [f"{p}/{m}" for p, m in spec.chain]
    if spec.flagship is not None:
        admitted.append(f"{spec.flagship[0]}/{spec.flagship[1]} (flagship)")
    for p, m in spec.flagship_voices:
        admitted.append(f"{p}/{m} (flagship voice)")
    return Decision(
        False, stamp, "class-mismatch",
        f"class {spec.class_id} admits [{'; '.join(admitted)}]; "
        f"requested {provider}/{model} refuses")
