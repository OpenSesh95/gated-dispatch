"""Swarm-pattern promotion path (cluster enablement, ratified 2026-11-13).

The rule, encoded where the gate's dispatch logic lives:
- A swarm pattern that BEATS its class single-seat baseline at the eval
  gate may staff WORKER FLOORS ONLY: junior panels, commodity mesh legs,
  commission swarm legs. At this gate those floors are the classes
  junior / lower-order / defect (a commission's swarm LEG dispatches as
  lower-order; the commission class itself is deliberative).
- The RATIFICATION FLOOR stays fixed named seats: the classes ruling,
  commission and panel REFUSE assembly patterns mechanically — this is a
  code refusal in the dispatch path, not a comment or a convention.
- Rule 2 containment binds every promoted pattern: its registry row must
  name its containment (a deterministic form gate or a higher-tier
  verifier inside the tagged assembly) or it does not promote.

The registry is append-only (docs/promotion-registry.jsonl). A pattern
enters it only with eval-gate evidence that it beat its baseline; a tie
does not promote.
"""
import json
import os

WORKER_FLOORS = {"junior", "lower-order", "defect"}
RATIFICATION_CLASSES = {"ruling", "commission", "panel"}
CONTAINMENTS = {"form-gate", "verifier"}

_REGISTRY = os.path.join(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__))), "docs", "promotion-registry.jsonl")


def load_registry(path=None):
    rows = {}
    p = path or _REGISTRY
    if os.path.exists(p):
        with open(p) as fh:
            for line in fh:
                line = line.strip()
                if line:
                    row = json.loads(line)
                    rows[row["pattern_id"]] = row
    return rows


def check_pattern(pattern_id, loop_class, registry_path=None):
    """-> (True, row) | (False, cause). Fail-closed on every doubt."""
    if loop_class in RATIFICATION_CLASSES:
        return False, ("ratification-floor: assembly patterns never staff "
                       f"class {loop_class}; named seats only")
    if loop_class not in WORKER_FLOORS:
        return False, f"class {loop_class} is not a worker floor"
    row = load_registry(registry_path).get(pattern_id)
    if row is None:
        return False, f"pattern {pattern_id} is not in the promotion registry"
    ev = row.get("eval_gate") or {}
    if ev.get("result") != "beat-baseline":
        return False, (f"pattern {pattern_id} carries no beat-baseline "
                       "eval-gate evidence")
    if row.get("containment") not in CONTAINMENTS:
        return False, (f"pattern {pattern_id} names no Rule 2 containment "
                       "(form-gate | verifier)")
    if not row.get("swarm_tag"):
        return False, f"pattern {pattern_id} carries no swarm_tag"
    return True, row
