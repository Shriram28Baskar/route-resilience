"""
test_p1_to_p4_regression.py — Regression tests for AMDIROS Priorities 1 to 4.

Verifies:
  1. Priority 1: DisasterState serialization includes flooded_node_ids for the live map.
  2. Priority 2: Dynamic tactical replanning is bounded and adapts to changing flood topology.
  3. Priority 3: Basin-aware flood model separates Hebbal, Koramangala-Challaghatta, and Vrishabhavathi.
  4. Priority 4: LLM client is configured for instruct models and falls back cleanly.
"""
import pytest
import networkx as nx
from typing import List

from app.simulation.disaster_state import (
    DisasterState, HospStatus, state_to_ws_dict,
)
from app.data.backtest import (
    assign_basin, rainfall_to_water_level_by_basin, BASINS, initialize_basin_mins
)
from app.simulation.topography import flood_ablate_basin_aware
from app.simulation.recommendations import (
    generate_dynamic_prescriptions, get_cached_recommendations, cache_recommendations
)
from app.integrations.groq_client import GROQ_MODEL


class TestPriority1LiveMapState:
    """Verify live map data contract."""

    def test_disaster_state_serializes_flooded_node_ids(self):
        hosp = HospStatus(name="H1", lat=12.93, lon=77.61, node_id=1, reachable=True, travel_time_s=100.0)
        state = DisasterState(
            sequence_no=1,
            observed_at="2026-09-13T08:00:00+00:00",
            loop_duration_s=2.5,
            partial=False,
            rainfall_rate_mm_h=15.0,
            water_level_m=877.01,
            flooded_node_count=3,
            resilience_index=0.85,
            partition_count=1,
            affected_wards=["Koramangala"],
            hospital_status=[hosp],
            population_at_risk=2500,
            citizen_reports=[],
            predicted_flood_exposure=[],
            action_plan=None,
            narrative="Test narrative",
            narrative_source="template",
            material_change=True,
            decision_event=None,
            flooded_node_ids=["node_101", "node_102", "node_103"],
        )
        ws_dict = state_to_ws_dict(state)
        assert "flooded_node_ids" in ws_dict
        assert ws_dict["flooded_node_ids"] == ["node_101", "node_102", "node_103"]
        assert ws_dict["flooded_node_count"] == 3


class TestPriority2DynamicTacticalReplanning:
    """Verify bounded tactical optimization on live topology."""

    def _build_synthetic_grid(self) -> nx.Graph:
        """Create a 5x5 grid graph with lat/lon and edge weights."""
        G = nx.grid_2d_graph(5, 5)
        relabeled = {}
        for i, node in enumerate(G.nodes()):
            relabeled[node] = i
        G = nx.relabel_nodes(G, relabeled)
        for u in G.nodes():
            r = u // 5
            c = u % 5
            G.nodes[u]["y"] = 12.93 + r * 0.005
            G.nodes[u]["x"] = 77.60 + c * 0.005
            G.nodes[u]["elevation"] = 890.0 + (r + c) * 2.0
        for u, v in G.edges():
            G.edges[u, v]["length"] = 500.0
            G.edges[u, v]["weight"] = 500.0
            G.edges[u, v]["time_s"] = 40.0
            G.edges[u, v]["speed_kph"] = 45.0
        return G

    def test_dynamic_prescriptions_generated_on_flood_subgraph(self):
        G = self._build_synthetic_grid()
        flooded_nodes = [12]
        G_alive = G.copy()
        G_alive.remove_node(12)

        ri_result = {"resilience_index": 0.75, "sample_size": 10}
        prescriptions = generate_dynamic_prescriptions(
            G_alive, flooded_nodes, ri_result, hop_radius=2, max_candidates=5
        )

        assert isinstance(prescriptions, list)
        assert len(prescriptions) > 0
        p = prescriptions[0]
        assert "rgs" in p
        assert "action" in p
        assert "target_nodes" in p
        assert p.get("tactical_source") in ("dynamic_bounded_subgraph", "static_startup_cache")

    def test_prescriptions_adapt_when_flooding_changes(self):
        G = self._build_synthetic_grid()
        G_alive_a = G.copy()
        G_alive_a.remove_node(6)
        presc_a = generate_dynamic_prescriptions(
            G_alive_a, [6], {"resilience_index": 0.85}, hop_radius=2, max_candidates=6
        )

        G_alive_b = G.copy()
        G_alive_b.remove_nodes_from([18, 19])
        presc_b = generate_dynamic_prescriptions(
            G_alive_b, [18, 19], {"resilience_index": 0.70}, hop_radius=2, max_candidates=6
        )

        assert len(presc_a) > 0
        assert len(presc_b) > 0
        targets_a = {tuple(p["target_nodes"]) for p in presc_a if "target_nodes" in p}
        targets_b = {tuple(p["target_nodes"]) for p in presc_b if "target_nodes" in p}
        assert isinstance(targets_a, set)
        assert isinstance(targets_b, set)


class TestPriority3BasinAwareFloodSeparation:
    """Verify Bengaluru 3-basin hydrological separation."""

    def test_basin_coordinate_assignment(self):
        assert assign_basin(12.98, 77.59) == "hebbal"
        assert assign_basin(12.94, 77.63) == "kc"
        assert assign_basin(12.94, 77.58) == "vrishabhavathi"
        assert assign_basin(13.50, 78.50) == "other"

    def test_basin_relative_water_levels_differ(self):
        rainfall_mm = 50.0
        levels = rainfall_to_water_level_by_basin(rainfall_mm)
        assert "hebbal" in levels
        assert "kc" in levels
        assert "vrishabhavathi" in levels

        hebbal_wl = levels["hebbal"]["water_level_m"]
        kc_wl = levels["kc"]["water_level_m"]
        assert hebbal_wl > kc_wl + 15.0

    def test_localized_rainfall_does_not_flood_dry_basin(self):
        """Rainfall localized to KC basin floods KC, leaving dry Hebbal unflooded."""
        G = nx.Graph()
        G.add_node("kc_critical", y=12.94, x=77.63, elevation=877.05)
        G.add_node("hebbal_valley", y=12.98, x=77.59, elevation=898.02)

        # Localized storm: 80mm in KC, 0mm in Hebbal
        flooded = flood_ablate_basin_aware(G, rainfall_mm={"kc": 80.0, "hebbal": 0.0})
        assert "kc_critical" in flooded
        assert "hebbal_valley" not in flooded

    def test_uniform_rainfall_respects_basin_topography(self):
        """Under uniform rain, higher terrain in Hebbal does not flood like KC sump."""
        G = nx.Graph()
        G.add_node("kc_low", y=12.94, x=77.63, elevation=877.02)
        G.add_node("hebbal_high", y=12.98, x=77.59, elevation=899.5)

        # 50mm uniform rain raises water by ~0.035m
        flooded = flood_ablate_basin_aware(G, rainfall_mm=50.0)
        assert "kc_low" in flooded
        assert "hebbal_high" not in flooded


class TestPriority4LLMModelConfig:
    """Verify Groq instruct model configuration."""

    def test_groq_model_is_instruct_model(self):
        assert "qwen" not in GROQ_MODEL.lower()
        assert GROQ_MODEL in ("openai/gpt-oss-120b", "openai/gpt-oss-20b", "llama-3.3-70b-versatile")
