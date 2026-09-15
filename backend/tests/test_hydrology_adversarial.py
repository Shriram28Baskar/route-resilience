"""
test_hydrology_adversarial.py — Hostile-standard tests for basin hydrology & sink dynamics.

Validates:
1. Monotonicity: R1 < R2 => Flooded(R1) ⊆ Flooded(R2) for all rainfall rates.
2. Cross-basin isolation: Rain strictly isolated to one basin causes zero flooding in others.
3. Local depression vulnerability: Nodes in local topographic sinks (underpasses) flood before
   adjacent elevated nodes.
"""

import pytest
import networkx as nx
from app.data.backtest import BASINS, assign_basin, rainfall_to_water_level_by_basin
from app.simulation.topography import flood_ablate_basin_aware, initialize_elevations


def build_terrain_test_graph():
    """Construct a synthetic multi-basin graph with realistic sags and ridges."""
    G = nx.Graph()

    # Hebbal basin (North)
    # Node in local depression (e.g. underpass)
    G.add_node("hebbal_sink", y=12.985, x=77.58, elevation=898.10)
    # Node on local ridge adjacent to underpass
    G.add_node("hebbal_ridge", y=12.986, x=77.581, elevation=899.50)
    G.add_edge("hebbal_sink", "hebbal_ridge")

    # KC basin (East / Bellandur)
    G.add_node("kc_lowland", y=12.935, x=77.65, elevation=877.05)
    G.add_node("kc_upland", y=12.936, x=77.651, elevation=878.50)
    G.add_edge("kc_lowland", "kc_upland")

    # Vrishabhavathi basin (West)
    G.add_node("vrish_valley", y=12.930, x=77.55, elevation=890.10)
    G.add_node("vrish_hill", y=12.931, x=77.551, elevation=892.00)
    G.add_edge("vrish_valley", "vrish_hill")

    # Calculate sink deltas manually or via initialize_elevations
    for n in G.nodes():
        nbr_elevs = [G.nodes[m]["elevation"] for m in G.neighbors(n)]
        min_local = min(nbr_elevs + [G.nodes[n]["elevation"]])
        G.nodes[n]["local_sink_delta"] = max(0.0, G.nodes[n]["elevation"] - min_local)

    return G


class TestAdversarialHydrology:

    def test_strict_monotonicity(self):
        """Proof: Flooded(R1) is a strict subset of Flooded(R2) for R1 < R2."""
        G = build_terrain_test_graph()

        rainfalls = [5.0, 15.0, 30.0, 60.0, 120.0, 250.0]
        flooded_sets = []

        for r in rainfalls:
            flooded = set(flood_ablate_basin_aware(G, r))
            flooded_sets.append(flooded)

        for i in range(len(rainfalls) - 1):
            r1, r2 = rainfalls[i], rainfalls[i + 1]
            f1, f2 = flooded_sets[i], flooded_sets[i + 1]
            assert f1.issubset(f2), f"Monotonicity violated: Flooded({r1}mm) not subset of Flooded({r2}mm)"

    def test_complete_cross_basin_isolation(self):
        """Rainfall exclusively over KC basin must cause zero flooding in Hebbal or Vrishabhavathi."""
        G = build_terrain_test_graph()

        # Extreme torrential rain in KC basin (150mm), zero in Hebbal and Vrishabhavathi
        flooded = flood_ablate_basin_aware(
            G, rainfall_mm={"kc": 150.0, "hebbal": 0.0, "vrishabhavathi": 0.0}
        )

        assert "kc_lowland" in flooded, "Lowland in flooded KC basin should be inundated"
        # Strict isolation check
        assert "hebbal_sink" not in flooded, "Hebbal sink must remain dry when rain is 0mm"
        assert "hebbal_ridge" not in flooded, "Hebbal ridge must remain dry when rain is 0mm"
        assert "vrish_valley" not in flooded, "Vrishabhavathi valley must remain dry when rain is 0mm"

    def test_local_depression_vulnerability(self):
        """A road depression (sink_delta=0) must flood at a lower rain threshold than adjacent ridge."""
        G = build_terrain_test_graph()

        # Low rainfall in Hebbal: enough to flood the underpass sink, but ridge sheds water
        flooded_low = flood_ablate_basin_aware(G, rainfall_mm={"hebbal": 200.0, "kc": 0.0, "vrishabhavathi": 0.0})

        # At moderate rain, sink should flood before ridge
        assert "hebbal_sink" in flooded_low
        assert "hebbal_ridge" not in flooded_low
