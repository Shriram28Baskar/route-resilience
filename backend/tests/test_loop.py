"""
test_loop.py — Tests for the AMDIROS autonomous loop components.

Tests:
  - Material change gate (evaluate_delta)
  - Projected Flood Exposure ETA direction property
  - Evacuation advisory classification rules
  - Citizen evidence independence (no graph mutation)
  - ActionPlan is built by build_action_plan (not LLM)
  - should_invoke_llm boundary conditions
  - StateRingBuffer seq numbering and capacity
"""
import math
import pytest
import networkx as nx

# ── disaster_state imports ─────────────────────────────────────────────────────
from app.simulation.disaster_state import (
    DisasterState, ActionPlan, HospStatus, NodeETA, EvacAdvisory,
    CitizenEvidence, CitizenEvidenceStore,
    StateRingBuffer, build_template_narrative, heartbeat_dict,
)

# ── decision_engine imports ────────────────────────────────────────────────────
from app.simulation.decision_engine import (
    evaluate_delta, should_invoke_llm, build_action_plan,
    DELTA_FLOOD_NODES_THRESHOLD, DELTA_RESILIENCE_THRESHOLD,
)

# ── projected_flood_exposure imports ──────────────────────────────────────────
from app.simulation.projected_flood_exposure import (
    predict_flood_exposure_eta, risk_label_for_eta,
)

# ── evacuation_advisory imports ────────────────────────────────────────────────
from app.simulation.evacuation_advisory import generate_evacuation_advisories


# ── Helpers ───────────────────────────────────────────────────────────────────

def _make_state(
    seq=1,
    flooded_node_count=100,
    resilience_index=0.8,
    water_level_m=880.0,
    rainfall_mm_h=10.0,
    hospital_reachable=True,
    citizen_reports=None,
):
    hosp = HospStatus(
        name="Test Hospital", lat=12.93, lon=77.61,
        node_id=1, reachable=hospital_reachable, travel_time_s=300.0,
    )
    return DisasterState(
        sequence_no=seq,
        observed_at="2026-09-13T08:00:00+00:00",
        loop_duration_s=5.0,
        partial=False,
        rainfall_rate_mm_h=rainfall_mm_h,
        water_level_m=water_level_m,
        flooded_node_count=flooded_node_count,
        resilience_index=resilience_index,
        partition_count=1,
        affected_wards=["Koramangala"],
        hospital_status=[hosp],
        population_at_risk=50000,
        citizen_reports=citizen_reports or [],
        predicted_flood_exposure=[],
        action_plan=None,
        narrative="",
        narrative_source="template",
        material_change=False,
        decision_event=None,
    )


def _make_alive_graph(node_elevations: dict) -> nx.Graph:
    """Build a minimal alive graph with elevation attributes on nodes."""
    G = nx.Graph()
    for node_id, (lat, lon, elev) in node_elevations.items():
        G.add_node(node_id, y=lat, x=lon, elevation=elev)
    return G


# ── evaluate_delta tests ───────────────────────────────────────────────────────

class TestEvaluateDelta:

    def test_first_activation_always_high(self):
        state = _make_state(seq=1)
        is_material, severity, reason, components = evaluate_delta(None, state)
        assert is_material is True
        assert severity == "HIGH"
        assert "First activation" in reason

    def test_no_change_returns_false(self):
        prev = _make_state(seq=1, flooded_node_count=100, resilience_index=0.80, water_level_m=880.0)
        new  = _make_state(seq=2, flooded_node_count=100, resilience_index=0.80, water_level_m=880.0)
        is_material, severity, reason, components = evaluate_delta(prev, new)
        assert is_material is False

    def test_hospital_isolation_triggers_high(self):
        prev = _make_state(seq=1, hospital_reachable=True)
        new  = _make_state(seq=2, hospital_reachable=False)
        is_material, severity, reason, components = evaluate_delta(prev, new)
        assert is_material is True
        assert severity == "HIGH"
        assert "hospital_isolation" in components

    def test_hospital_restoration_triggers_high(self):
        prev = _make_state(seq=1, hospital_reachable=False)
        new  = _make_state(seq=2, hospital_reachable=True)
        is_material, severity, reason, components = evaluate_delta(prev, new)
        assert is_material is True
        assert severity == "HIGH"

    def test_large_ri_drop_triggers_high(self):
        prev = _make_state(seq=1, resilience_index=0.90)
        new  = _make_state(seq=2, resilience_index=0.70)  # 0.20 drop > 0.15 threshold
        is_material, severity, _, components = evaluate_delta(prev, new)
        assert is_material is True
        assert severity == "HIGH"
        assert "resilience_index" in components

    def test_medium_ri_drop_triggers_medium(self):
        prev = _make_state(seq=1, resilience_index=0.80, hospital_reachable=True,
                           flooded_node_count=100, water_level_m=880.0)
        new  = _make_state(seq=2, resilience_index=0.74, hospital_reachable=True,
                           flooded_node_count=100, water_level_m=880.0)  # 0.06 drop
        is_material, severity, _, components = evaluate_delta(prev, new)
        assert is_material is True
        assert severity == "MEDIUM"

    def test_flood_node_delta_triggers_medium(self):
        prev = _make_state(seq=1, flooded_node_count=100, resilience_index=0.80,
                           water_level_m=880.0, hospital_reachable=True)
        new  = _make_state(seq=2, flooded_node_count=106, resilience_index=0.80,
                           water_level_m=880.0, hospital_reachable=True)  # delta=6 > threshold=5
        is_material, severity, _, components = evaluate_delta(prev, new)
        assert is_material is True
        assert severity == "MEDIUM"
        assert "flood_extent" in components

    def test_small_flood_delta_no_change(self):
        prev = _make_state(seq=1, flooded_node_count=100, resilience_index=0.80,
                           water_level_m=880.0, hospital_reachable=True)
        new  = _make_state(seq=2, flooded_node_count=102, resilience_index=0.80,
                           water_level_m=880.0, hospital_reachable=True)  # delta=2 < threshold=5
        is_material, _, _, _ = evaluate_delta(prev, new)
        assert is_material is False

    def test_citizen_flooding_report_triggers_medium(self):
        report = CitizenEvidence(
            report_id="abc", lat=12.93, lon=77.61,
            message="Road flooded", severity="high",
            snapped_node_id=42, flooding_indicator=True,
            received_at="2026-09-13T08:00:00Z",
            twin_agreement="UNVERIFIABLE", twin_note="",
        )
        prev = _make_state(seq=1)
        new  = _make_state(seq=2, citizen_reports=[report])
        is_material, severity, _, components = evaluate_delta(prev, new)
        assert is_material is True
        assert severity in ("MEDIUM", "HIGH")
        assert "citizen_evidence" in components


# ── should_invoke_llm tests ───────────────────────────────────────────────────

class TestShouldInvokeLLM:

    def test_first_activation_always_true(self):
        assert should_invoke_llm("MEDIUM", is_first_activation=True) is True
        assert should_invoke_llm("LOW", is_first_activation=True) is True
        assert should_invoke_llm("", is_first_activation=True) is True

    def test_high_severity_true(self):
        assert should_invoke_llm("HIGH", is_first_activation=False) is True

    def test_medium_false(self):
        assert should_invoke_llm("MEDIUM", is_first_activation=False) is False

    def test_low_false(self):
        assert should_invoke_llm("LOW", is_first_activation=False) is False

    def test_empty_severity_false(self):
        assert should_invoke_llm("", is_first_activation=False) is False


# ── build_action_plan tests ────────────────────────────────────────────────────

class TestBuildActionPlan:

    def test_returns_action_plan(self):
        hosps = [HospStatus("H1", 12.93, 77.61, 1, True, 300.0)]
        plan = build_action_plan(
            sequence_no=3,
            camps_result={"camps": [{"id": "c1", "lat": 12.94, "lng": 77.61}]},
            advisories=[],
            prescriptions=[],
            hospital_status=hosps,
            population_at_risk=50000,
            resilience_index=0.75,
            affected_wards=["Koramangala"],
        )
        assert isinstance(plan, ActionPlan)
        assert plan.sequence_no == 3
        assert len(plan.relief_camp_positions) == 1
        assert plan.hospitals_isolated == 0
        assert plan.resilience_index == 0.75

    def test_counts_isolated_hospitals(self):
        hosps = [
            HospStatus("H1", 12.93, 77.61, 1, True, 300.0),
            HospStatus("H2", 12.94, 77.62, 2, False, None),
        ]
        plan = build_action_plan(
            sequence_no=4,
            camps_result={"camps": []},
            advisories=[],
            prescriptions=[],
            hospital_status=hosps,
            population_at_risk=0,
            resilience_index=None,
            affected_wards=[],
        )
        assert plan.hospitals_isolated == 1


# ── Projected Flood Exposure ETA tests ────────────────────────────────────────

class TestProjectedFloodExposure:

    def test_lower_elevation_lower_eta(self):
        """Property: lower elevation → lower ETA (floods sooner)."""
        G = _make_alive_graph({
            1: (12.93, 77.61, 880.005),   # 5mm above water
            2: (12.94, 77.62, 880.010),   # 10mm above water
            3: (12.95, 77.63, 880.015),   # 15mm above water
        })
        results = predict_flood_exposure_eta(G, water_level_m=880.0, rainfall_rate_mm_h=20.0)
        assert len(results) == 3
        # Sorted ascending by eta
        etas = [r["eta_minutes"] for r in results]
        assert etas == sorted(etas)
        assert etas[0] < etas[1] < etas[2]

    def test_no_rain_returns_empty(self):
        G = _make_alive_graph({1: (12.93, 77.61, 880.005)})
        results = predict_flood_exposure_eta(G, water_level_m=880.0, rainfall_rate_mm_h=0.0)
        assert results == []

    def test_already_flooded_nodes_skipped(self):
        """Nodes at or below water_level_m should not appear in predictions."""
        G = _make_alive_graph({
            1: (12.93, 77.61, 879.99),    # below water level — should be skipped
            2: (12.94, 77.62, 880.005),   # above water level — should appear
        })
        results = predict_flood_exposure_eta(G, water_level_m=880.0, rainfall_rate_mm_h=20.0)
        node_ids = [r["node_id"] for r in results]
        assert "1" not in node_ids
        assert "2" in node_ids

    def test_data_type_always_extrapolated(self):
        G = _make_alive_graph({1: (12.93, 77.61, 880.005)})
        results = predict_flood_exposure_eta(G, water_level_m=880.0, rainfall_rate_mm_h=20.0)
        assert len(results) == 1
        for r in results:
            assert r["data_type"] == "EXTRAPOLATED"
            assert r["projection_basis"] == "linear_effective_runoff_persistence"

    def test_beyond_horizon_excluded(self):
        """Nodes that flood beyond 90 minutes should not appear."""
        G = _make_alive_graph({1: (12.93, 77.61, 999.0)})  # very high elevation
        results = predict_flood_exposure_eta(
            G, water_level_m=880.0, rainfall_rate_mm_h=5.0, horizon_minutes=90
        )
        assert results == []

    def test_risk_labels(self):
        assert risk_label_for_eta(5.0)   == "imminent"
        assert risk_label_for_eta(20.0)  == "critical"
        assert risk_label_for_eta(45.0)  == "warning"
        assert risk_label_for_eta(75.0)  == "watch"


# ── Evacuation advisory classification tests ──────────────────────────────────

class TestEvacuationAdvisoryClassification:

    def _run(self, flooded_count, hospital_reachable, ri):
        from app.simulation.evacuation_advisory import _classify_action
        return _classify_action(flooded_count, hospital_reachable, ri)

    def test_hospital_isolated_gives_evacuate_now(self):
        assert self._run(5, False, 0.8) == "EVACUATE_NOW"

    def test_low_ri_gives_evacuate_now(self):
        assert self._run(5, True, 0.4) == "EVACUATE_NOW"

    def test_high_flood_count_gives_evacuate_now(self):
        assert self._run(51, True, 0.8) == "EVACUATE_NOW"

    def test_medium_flood_with_ok_ri_gives_advised(self):
        assert self._run(20, True, 0.65) == "EVACUATE_ADVISED"

    def test_low_flood_high_ri_gives_monitor(self):
        assert self._run(3, True, 0.85) == "MONITOR"

    def test_unknown_ri_with_moderate_flood_gives_advised(self):
        # RI = None and flooded_count > 5 → EVACUATE_ADVISED (hospital reachable)
        assert self._run(20, True, None) == "EVACUATE_ADVISED"


# ── CitizenEvidenceStore independence tests ────────────────────────────────────

class TestCitizenEvidenceStore:

    def test_add_does_not_mutate_graph(self):
        """Critical: citizen reports must never touch graph state."""
        G = _make_alive_graph({1: (12.93, 77.61, 882.0)})
        original_elev = G.nodes[1]["elevation"]

        store = CitizenEvidenceStore()
        report = CitizenEvidence(
            report_id="test-123", lat=12.93, lon=77.61,
            message="Road flooded here", severity="high",
            snapped_node_id=1, flooding_indicator=True,
            received_at="2026-09-13T08:00:00Z",
            twin_agreement="DISAGREES",
            twin_note="Citizen reports flooding but twin shows node above water.",
        )
        store.add(report)

        # Graph must be completely unchanged
        assert G.nodes[1]["elevation"] == original_elev
        assert 1 not in [n for n in G.nodes if G.nodes[n].get("citizen_flagged")]

    def test_drain_clears_pending(self):
        store = CitizenEvidenceStore()
        store.add(CitizenEvidence(
            report_id="a", lat=12.93, lon=77.61, message="flood",
            severity="high", snapped_node_id=1, flooding_indicator=True,
            received_at="2026-09-13T08:00:00Z",
            twin_agreement="UNVERIFIABLE", twin_note="",
        ))
        drained = store.drain()
        assert len(drained) == 1
        # Second drain returns empty
        assert store.drain() == []

    def test_all_history_retained_after_drain(self):
        store = CitizenEvidenceStore()
        for i in range(3):
            store.add(CitizenEvidence(
                report_id=str(i), lat=12.93, lon=77.61, message="test",
                severity="low", snapped_node_id=1, flooding_indicator=False,
                received_at="2026-09-13T08:00:00Z",
                twin_agreement="UNVERIFIABLE", twin_note="",
            ))
        store.drain()
        recent = store.get_recent(10)
        assert len(recent) == 3  # still in history after drain

    def test_has_pending_flooding_reports(self):
        store = CitizenEvidenceStore()
        assert store.has_pending_flooding_reports() is False
        store.add(CitizenEvidence(
            report_id="b", lat=12.93, lon=77.61, message="flood",
            severity="high", snapped_node_id=1, flooding_indicator=True,
            received_at="2026-09-13T08:00:00Z",
            twin_agreement="UNVERIFIABLE", twin_note="",
        ))
        assert store.has_pending_flooding_reports() is True


# ── StateRingBuffer tests ──────────────────────────────────────────────────────

class TestStateRingBuffer:

    def test_seq_starts_at_one(self):
        buf = StateRingBuffer()
        assert buf.next_seq() == 1
        assert buf.next_seq() == 2

    def test_capacity_enforced(self):
        buf = StateRingBuffer()
        for i in range(StateRingBuffer.MAX_HISTORY + 5):
            s = _make_state(seq=i+1)
            buf.push(s)
        assert len(buf.get_all()) == StateRingBuffer.MAX_HISTORY

    def test_get_latest_returns_last_pushed(self):
        buf = StateRingBuffer()
        s1 = _make_state(seq=1)
        s2 = _make_state(seq=2)
        buf.push(s1)
        buf.push(s2)
        assert buf.get_latest().sequence_no == 2

    def test_get_n_returns_last_n(self):
        buf = StateRingBuffer()
        for i in range(5):
            buf.push(_make_state(seq=i+1))
        last3 = buf.get_n(3)
        assert len(last3) == 3
        assert last3[-1].sequence_no == 5


# ── heartbeat_dict test ────────────────────────────────────────────────────────

def test_heartbeat_dict_type():
    hb = heartbeat_dict(seq=5, observed_at="2026-09-13T08:00:00Z",
                        rainfall=12.5, retained_from=4)
    assert hb["type"] == "LOOP_HEARTBEAT"
    assert hb["material_change"] is False
    assert hb["sequence_no"] == 5
    assert hb["retained_from_seq"] == 4


# ── Template narrative smoke test ─────────────────────────────────────────────

def test_build_template_narrative_runs():
    state = _make_state(seq=7, flooded_node_count=450, resilience_index=0.62)
    narrative = build_template_narrative(state)
    # Narrative uses bullet-point format; "Loop #N" header was removed in favour of
    # a structured bullet list.  Verify the key facts are present.
    assert "450" in narrative          # flooded node count
    assert "0.62" in narrative         # resilience index
    assert "Situation" in narrative    # first bullet present
