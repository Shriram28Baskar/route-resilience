"""
decision_engine.py — Material change gate and ActionPlan builder.

Architecture: PREDICT → DECIDE → ActionPlan → ACT

Invariants:
  - All outputs are deterministic. No LLM involvement.
  - build_action_plan() is the only constructor for ActionPlan.
  - evaluate_delta() is the only gating function for state transitions.
  - should_invoke_llm() controls narrative generation; it has no write access
    to ActionPlan or DisasterState.
"""
import logging
from datetime import datetime, timezone
from typing import List, Optional, Tuple

from app.simulation.disaster_state import (
    DisasterState, DecisionEvent, ActionPlan, EvacAdvisory, HospStatus
)

logger = logging.getLogger(__name__)

# ── Material change thresholds ─────────────────────────────────────────────────
DELTA_FLOOD_NODES_THRESHOLD  = 5
DELTA_RESILIENCE_THRESHOLD   = 0.05   # 5% RI drop → MEDIUM
DELTA_RESILIENCE_HIGH        = 0.15   # 15% RI drop → HIGH
DELTA_WATER_LEVEL_THRESHOLD  = 0.002  # 2mm rise → MEDIUM


def evaluate_delta(
    prev: Optional[DisasterState],
    new_state: DisasterState,
) -> Tuple[bool, str, str, List[str]]:
    """
    Compare new observation against previous state.

    Returns:
        (is_material_change, severity, trigger_reason, changed_components)

    Severity levels:
        "HIGH"   — hospital isolation changed, or RI drops > 15%
        "MEDIUM" — flood nodes delta > 5, RI drops 5-15%, water rises > 2mm,
                   or citizen flooding report received
        "LOW"    — minor citizen report (no flooding indicator)
        ""       — no material change

    First activation (prev is None) always returns HIGH.
    """
    if prev is None:
        return True, "HIGH", "First activation", ["all"]

    changed: List[str] = []
    severity = ""
    reasons: List[str] = []

    # ── Hospital isolation change → HIGH ──────────────────────────────────────
    prev_isolated = {h.name for h in prev.hospital_status if not h.reachable}
    new_isolated  = {h.name for h in new_state.hospital_status if not h.reachable}
    if prev_isolated != new_isolated:
        changed.append("hospital_isolation")
        newly_isolated = new_isolated - prev_isolated
        newly_restored = prev_isolated - new_isolated
        if newly_isolated:
            if len(newly_isolated) <= 2:
                reasons.append(f"{', '.join(newly_isolated)} hospital(s) now isolated")
            else:
                top_sample = list(newly_isolated)[:2]
                reasons.append(f"{len(newly_isolated)} hospitals isolated ({', '.join(top_sample)} +{len(newly_isolated)-2} more)")
        if newly_restored:
            if len(newly_restored) <= 2:
                reasons.append(f"{', '.join(newly_restored)} hospital(s) restored")
            else:
                top_sample = list(newly_restored)[:2]
                reasons.append(f"{len(newly_restored)} hospitals restored ({', '.join(top_sample)} +{len(newly_restored)-2} more)")
        severity = "HIGH"

    # ── Resilience Index drop ─────────────────────────────────────────────────
    if prev.resilience_index is not None and new_state.resilience_index is not None:
        ri_drop = prev.resilience_index - new_state.resilience_index
        if ri_drop > DELTA_RESILIENCE_HIGH:
            changed.append("resilience_index")
            reasons.append(f"RI dropped {ri_drop:.2%} (HIGH)")
            severity = "HIGH"
        elif ri_drop > DELTA_RESILIENCE_THRESHOLD:
            changed.append("resilience_index")
            reasons.append(f"RI dropped {ri_drop:.2%}")
            if severity != "HIGH":
                severity = "MEDIUM"

    # ── Flood node count change ───────────────────────────────────────────────
    flood_delta = abs(new_state.flooded_node_count - prev.flooded_node_count)
    if flood_delta >= DELTA_FLOOD_NODES_THRESHOLD:
        changed.append("flood_extent")
        reasons.append(f"Flood nodes changed by {flood_delta}")
        if severity not in ("HIGH",):
            severity = "MEDIUM"

    # ── Water level rise ──────────────────────────────────────────────────────
    wl_delta = new_state.water_level_m - prev.water_level_m
    if wl_delta > DELTA_WATER_LEVEL_THRESHOLD:
        changed.append("water_level")
        reasons.append(f"Water level +{wl_delta*1000:.1f}mm")
        if severity not in ("HIGH",):
            severity = "MEDIUM"

    # ── Ward footprint change ─────────────────────────────────────────────────
    if set(new_state.affected_wards) != set(prev.affected_wards):
        changed.append("affected_wards")
        if severity not in ("HIGH", "MEDIUM"):
            severity = "MEDIUM"
            reasons.append("Affected wards changed")

    # ── Citizen evidence with flooding indicator ──────────────────────────────
    flooding_reports = [r for r in new_state.citizen_reports if r.flooding_indicator]
    if flooding_reports:
        changed.append("citizen_evidence")
        reasons.append(f"{len(flooding_reports)} citizen flooding report(s) received")
        if severity not in ("HIGH", "MEDIUM"):
            severity = "MEDIUM"
    elif new_state.citizen_reports:
        changed.append("citizen_evidence")
        if not severity:
            severity = "LOW"
            reasons.append("Citizen report received (no flooding indicator)")

    is_material = bool(changed)
    trigger_reason = "; ".join(reasons) if reasons else "No material change"
    return is_material, severity, trigger_reason, changed


def classify_changed_components(
    prev: Optional[DisasterState],
    new_state: DisasterState,
) -> List[str]:
    """Return list of changed component names (subset of evaluate_delta logic)."""
    _, _, _, changed = evaluate_delta(prev, new_state)
    return changed


def should_invoke_llm(severity: str, is_first_activation: bool) -> bool:
    """
    Returns True only when:
      - is_first_activation == True (loop #1), OR
      - severity == "HIGH" (hospital isolation, major RI drop)

    Never invoked for MEDIUM, LOW, or no-change iterations.
    LLM has zero write access to ActionPlan or any operational variable.
    """
    return is_first_activation or severity == "HIGH"


def build_action_plan(
    sequence_no: int,
    camps_result: dict,
    advisories: List[EvacAdvisory],
    prescriptions: List[dict],
    hospital_status: List[HospStatus],
    population_at_risk: int,
    resilience_index: Optional[float],
    affected_wards: List[str],
) -> ActionPlan:
    """
    Assemble the complete ActionPlan from DECIDE-stage outputs.

    This function is the sole constructor for ActionPlan.
    It is deterministic — given the same inputs it produces the same plan.
    It does NOT call any LLM, make network requests, or mutate graph state.
    """
    camps = camps_result.get("camps", []) if camps_result else []
    isolated_count = sum(1 for h in hospital_status if not h.reachable)

    return ActionPlan(
        sequence_no=sequence_no,
        created_at=datetime.now(timezone.utc).isoformat(),
        relief_camp_positions=camps,
        evacuation_advisories=advisories,
        tactical_prescriptions=prescriptions,
        affected_ward_count=len(affected_wards),
        hospitals_isolated=isolated_count,
        population_at_risk=population_at_risk,
        resilience_index=resilience_index,
    )
