"""
disaster_state.py — Central state model for the AMDIROS autonomous loop.

Architecture:
  OBSERVE → FUSE → UNDERSTAND → PREDICT → DECIDE → ActionPlan → ACT → OBSERVE AGAIN

Key design invariants:
  - DisasterState is the immutable snapshot of one full observation cycle.
  - ActionPlan is produced by DECIDE (deterministic). ACT distributes it. LLM narrates it.
  - CitizenEvidence is an independent evidence layer stored in CitizenEvidenceStore.
    It NEVER mutates flooded_node_ids, elevations, graph connectivity, or water_level.
    Agreement/disagreement with the digital twin is computed and surfaced explicitly.
  - StateRingBuffer retains last MAX_HISTORY states (60 min at 5-min cadence; 12 min at 60s demo cadence).
"""

import threading
import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import List, Optional, Dict, Any

logger = logging.getLogger(__name__)

# ── Data provenance labels ─────────────────────────────────────────────────────
OBSERVED     = "OBSERVED"
DERIVED      = "DERIVED"
SIMULATED    = "SIMULATED"
EXTRAPOLATED = "EXTRAPOLATED"

ETA_PROJECTION_BASIS = "linear_effective_runoff_persistence"


# ── Node Flood Exposure ETA ────────────────────────────────────────────────────

@dataclass
class NodeETA:
    """
    Projected Flood Exposure ETA for a single graph node.
    data_type is always EXTRAPOLATED — never misrepresent as a forecast.
    """
    node_id: str
    lat: float
    lon: float
    elevation_m: float
    current_water_level_m: float
    delta_elevation_m: float
    eta_minutes: float
    risk_label: str           # "imminent" | "critical" | "warning" | "watch"
    data_type: str = EXTRAPOLATED
    projection_basis: str = ETA_PROJECTION_BASIS
    methodology_note: str = ""


# ── Hospital / Facility Status ─────────────────────────────────────────────────

@dataclass
class HospStatus:
    name: str
    lat: float
    lon: float
    node_id: Optional[int]
    reachable: bool
    travel_time_s: Optional[float]


# ── Evacuation Advisory ────────────────────────────────────────────────────────

@dataclass
class EvacAdvisory:
    ward_name: str
    action: str                   # "EVACUATE_NOW" | "EVACUATE_ADVISED" | "MONITOR"
    population_estimate: int
    population_source: str
    flooded_node_count: int
    nearest_camp_id: str
    recommended_corridor: str
    travel_time_estimate_s: float
    hospital_reachable: bool


# ── Decision Event ─────────────────────────────────────────────────────────────

@dataclass
class DecisionEvent:
    severity: str                 # "HIGH" | "MEDIUM" | "LOW"
    trigger_reason: str
    changed_components: List[str]
    previous_seq: int
    new_seq: int


# ── ActionPlan (DECIDE → ACT boundary) ────────────────────────────────────────

@dataclass
class ActionPlan:
    """
    Complete operational response produced by the DECIDE stage.

    DECIDE populates this deterministically. ACT distributes it via WebSocket/email/UI.
    LLM receives it as read-only context to narrate. No LLM involvement in production.

    Invariant: ActionPlan is immutable after build_action_plan() returns.
    """
    sequence_no: int
    created_at: str                        # ISO UTC datetime
    relief_camp_positions: List[Dict]      # from compute_relief_camps()
    evacuation_advisories: List[EvacAdvisory]
    tactical_prescriptions: List[Dict]     # from generate_recommendations / prescribe
    affected_ward_count: int
    hospitals_isolated: int
    population_at_risk: int
    resilience_index: Optional[float]


# ── Citizen Evidence (independent layer — never mutates physical truth) ────────

@dataclass
class CitizenEvidence:
    """
    An individual citizen distress report.

    Citizen evidence is stored in CitizenEvidenceStore independently of the
    digital twin. It NEVER modifies flooded_node_ids, water_level_m, elevations,
    or graph connectivity. Agreement/disagreement with the twin is computed
    separately and surfaced as an explicit signal.
    """
    report_id: str
    lat: float
    lon: float
    message: str
    severity: str                 # "critical" | "high" | "moderate" | "low"
    snapped_node_id: Optional[int]
    flooding_indicator: bool      # True if NLP keyword match detected flooding language
    received_at: str              # ISO UTC datetime
    # Evidence-vs-twin comparison (set after compare_with_twin())
    twin_agreement: str = "UNVERIFIABLE"  # "AGREES" | "DISAGREES" | "UNVERIFIABLE"
    twin_note: str = ""                   # explanation of (dis)agreement


class CitizenEvidenceStore:
    """
    Thread-safe store for citizen distress reports.

    This is completely separate from the graph or simulation state.
    Calling .add() NEVER modifies any graph node, edge, or simulation parameter.
    The .drain() method returns and clears pending reports for the next loop cycle.
    """
    MAX_STORED = 200

    def __init__(self):
        self._lock = threading.Lock()
        self._all: List[CitizenEvidence] = []        # persistent history
        self._pending: List[CitizenEvidence] = []    # cleared each loop

    def add(self, evidence: CitizenEvidence) -> None:
        with self._lock:
            self._pending.append(evidence)
            self._all.append(evidence)
            # Trim history
            if len(self._all) > self.MAX_STORED:
                self._all = self._all[-self.MAX_STORED:]

    def drain(self) -> List[CitizenEvidence]:
        """Return and clear pending evidence. Thread-safe."""
        with self._lock:
            pending = list(self._pending)
            self._pending = []
            return pending

    def has_pending_flooding_reports(self) -> bool:
        with self._lock:
            return any(e.flooding_indicator for e in self._pending)

    def get_recent(self, n: int = 50) -> List[CitizenEvidence]:
        with self._lock:
            return list(self._all[-n:])

    def clear_all(self) -> None:
        with self._lock:
            self._all = []
            self._pending = []


# Module-level store singleton
citizen_evidence_store = CitizenEvidenceStore()


# ── Disaster State ─────────────────────────────────────────────────────────────

@dataclass
class DisasterState:
    """
    Complete snapshot of one autonomous observation cycle.

    Fields are tagged with their data provenance label. The label is included
    in API responses to ensure transparency.
    """
    # Identity
    sequence_no: int
    observed_at: str           # ISO UTC datetime
    loop_duration_s: float
    partial: bool              # True if loop timed out before full completion

    # OBSERVE (data_type: OBSERVED)
    rainfall_rate_mm_h: float  # OWM rain.1h — OBSERVED
    water_level_m: float       # rainfall_to_water_level() — DERIVED

    # FUSE + UNDERSTAND (data_type: SIMULATED / DERIVED)
    flooded_node_count: int    # flood_ablate() — SIMULATED
    resilience_index: Optional[float]   # compute_resilience_index() — SIMULATED
    partition_count: int
    affected_wards: List[str]
    hospital_status: List[HospStatus]
    population_at_risk: int    # WorldPop spatial query — DERIVED

    # Citizen evidence snapshot (independent evidence layer)
    citizen_reports: List[CitizenEvidence]  # read-only snapshot for this cycle

    # PREDICT (data_type: EXTRAPOLATED)
    predicted_flood_exposure: List[NodeETA]  # EXTRAPOLATED

    # DECIDE → ActionPlan (all deterministic, no LLM)
    action_plan: Optional[ActionPlan]

    # ACT outputs
    narrative: str
    narrative_source: str      # "llm" | "template"

    # Change tracking
    material_change: bool
    decision_event: Optional[DecisionEvent]
    flooded_node_ids: List[str] = field(default_factory=list)


# ── State Ring Buffer ──────────────────────────────────────────────────────────

class StateRingBuffer:
    """
    Thread-safe ring buffer of the last MAX_HISTORY DisasterState snapshots.

    Capacity: MAX_HISTORY = 12.
    At 5-min production cadence: covers 60 minutes of history.
    At 60s demo cadence: covers 12 minutes of history.
    """
    MAX_HISTORY = 12

    def __init__(self):
        self._lock = threading.Lock()
        self._states: List[DisasterState] = []
        self._seq: int = 0

    def next_seq(self) -> int:
        with self._lock:
            self._seq += 1
            return self._seq

    def push(self, state: DisasterState) -> None:
        with self._lock:
            self._states.append(state)
            if len(self._states) > self.MAX_HISTORY:
                self._states = self._states[-self.MAX_HISTORY:]

    def get_all(self) -> List[DisasterState]:
        with self._lock:
            return list(self._states)

    def get_latest(self) -> Optional[DisasterState]:
        with self._lock:
            return self._states[-1] if self._states else None

    def get_n(self, n: int) -> List[DisasterState]:
        with self._lock:
            return list(self._states[-n:])


# Module-level singleton
state_ring_buffer = StateRingBuffer()


# ── Deterministic Template Narrative ──────────────────────────────────────────

def build_template_narrative(state: DisasterState) -> str:
    """
    Construct a factual, plain-English narrative from DisasterState fields.

    This is the default narrative when the LLM is not invoked (MEDIUM/LOW severity
    or LLM unavailable). It is deterministic, sub-millisecond, and has no external dependencies.
    """
    time_str = state.observed_at[:16].replace("T", " ") + " UTC" if state.observed_at else "Now"

    isolated_hospitals = [h.name for h in state.hospital_status if not h.reachable]
    reachable_hospitals = [h.name for h in state.hospital_status if h.reachable]

    evac_now = []
    evac_advised = []
    if state.action_plan:
        evac_now = [a.ward_name for a in state.action_plan.evacuation_advisories
                    if a.action == "EVACUATE_NOW"]
        evac_advised = [a.ward_name for a in state.action_plan.evacuation_advisories
                        if a.action == "EVACUATE_ADVISED"]

    ri_str = f"{state.resilience_index:.2f}" if state.resilience_index is not None else "N/A"
    bullets = [
        f"• Situation: {state.flooded_node_count} nodes flooded across {len(state.affected_wards)} ward(s) [SIMULATED] | Rain: {state.rainfall_rate_mm_h:.1f} mm/h [OBSERVED] | Threshold: {state.water_level_m:.3f}m [DERIVED]",
        f"• Resilience: Network RI {ri_str} [SIMULATED]",
    ]
    if isolated_hospitals:
        if len(isolated_hospitals) <= 2:
            bullets.append(f"• Healthcare: ⚠️ {', '.join(isolated_hospitals)} isolated from road network")
        else:
            bullets.append(f"• Healthcare: ⚠️ {len(isolated_hospitals)} hospitals isolated ({', '.join(isolated_hospitals[:2])} +{len(isolated_hospitals)-2} more)")
    elif reachable_hospitals:
        bullets.append(f"• Healthcare: ✓ All {len(reachable_hospitals)} hospitals reachable")

    if evac_now:
        bullets.append(f"• Evacuation: 🚨 EVACUATE NOW ordered for {', '.join(evac_now)}")
    elif evac_advised:
        bullets.append(f"• Evacuation: ⚠️ Advisory active for {', '.join(evac_advised)}")
    else:
        bullets.append("• Evacuation: ✓ No active evacuation orders")

    if state.action_plan and state.action_plan.relief_camp_positions:
        bullets.append(f"• Relief Camps: {len(state.action_plan.relief_camp_positions)} active relief hubs positioned on high ground")

    if state.predicted_flood_exposure:
        imminent = [n for n in state.predicted_flood_exposure if n.risk_label == "imminent"]
        if imminent:
            bullets.append(f"• Forecast: ⚠️ {len(imminent)} road node(s) projected to flood within 15 min [EXTRAPOLATED]")

    return "\n".join(bullets)


# ── WebSocket Serialisation ────────────────────────────────────────────────────

def _advisory_to_dict(a: EvacAdvisory) -> Dict:
    return {
        "ward_name": a.ward_name,
        "action": a.action,
        "population_estimate": a.population_estimate,
        "population_source": a.population_source,
        "flooded_node_count": a.flooded_node_count,
        "nearest_camp_id": a.nearest_camp_id,
        "recommended_corridor": a.recommended_corridor,
        "travel_time_estimate_s": a.travel_time_estimate_s,
        "hospital_reachable": a.hospital_reachable,
    }


def _citizen_to_dict(c: CitizenEvidence) -> Dict:
    return {
        "report_id": c.report_id,
        "lat": c.lat,
        "lon": c.lon,
        "message": c.message,
        "severity": c.severity,
        "snapped_node_id": c.snapped_node_id,
        "flooding_indicator": c.flooding_indicator,
        "received_at": c.received_at,
        "twin_agreement": c.twin_agreement,
        "twin_note": c.twin_note,
    }


def state_to_ws_dict(state: DisasterState) -> Dict[str, Any]:
    """Convert DisasterState to a JSON-serializable dict for WebSocket broadcast."""
    plan = state.action_plan
    return {
        "type": "DISASTER_STATE_UPDATE",
        "sequence_no": state.sequence_no,
        "observed_at": state.observed_at,
        "loop_duration_s": round(state.loop_duration_s, 2),
        "partial": state.partial,
        # OBSERVE
        "rainfall_rate_mm_h": state.rainfall_rate_mm_h,
        "water_level_m": state.water_level_m,
        # UNDERSTAND
        "flooded_node_count": state.flooded_node_count,
        "flooded_node_ids": [str(nid) for nid in getattr(state, "flooded_node_ids", [])],
        "resilience_index": state.resilience_index,
        "partition_count": state.partition_count,
        "affected_wards": state.affected_wards,
        "population_at_risk": state.population_at_risk,
        "hospital_status": [
            {
                "name": h.name, "lat": h.lat, "lon": h.lon,
                "reachable": h.reachable, "travel_time_s": h.travel_time_s,
            }
            for h in state.hospital_status
        ],
        # Citizen evidence (independent layer)
        "citizen_reports": [_citizen_to_dict(c) for c in state.citizen_reports],
        # PREDICT
        "predicted_flood_exposure": [
            {
                "node_id": n.node_id, "lat": n.lat, "lon": n.lon,
                "elevation_m": n.elevation_m, "eta_minutes": n.eta_minutes,
                "risk_label": n.risk_label,
                "data_type": n.data_type,
                "projection_basis": n.projection_basis,
            }
            for n in state.predicted_flood_exposure
        ],
        # ActionPlan (DECIDE output)
        "action_plan": {
            "sequence_no": plan.sequence_no,
            "created_at": plan.created_at,
            "relief_camps": plan.relief_camp_positions,
            "evacuation_advisories": [_advisory_to_dict(a) for a in plan.evacuation_advisories],
            "tactical_prescriptions": plan.tactical_prescriptions,
            "affected_ward_count": plan.affected_ward_count,
            "hospitals_isolated": plan.hospitals_isolated,
        } if plan else None,
        # ACT narrative
        "narrative": state.narrative,
        "narrative_source": state.narrative_source,
        # Change tracking
        "material_change": state.material_change,
        "decision_event": {
            "severity": state.decision_event.severity,
            "trigger_reason": state.decision_event.trigger_reason,
            "changed_components": state.decision_event.changed_components,
        } if state.decision_event else None,
    }


def heartbeat_dict(seq: int, observed_at: str, rainfall: float, retained_from: int) -> Dict:
    """Minimal WebSocket payload when no material change detected."""
    return {
        "type": "LOOP_HEARTBEAT",
        "sequence_no": seq,
        "observed_at": observed_at,
        "rainfall_rate_mm_h": rainfall,
        "material_change": False,
        "retained_from_seq": retained_from,
    }
