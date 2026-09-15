"""
test_dynamic_replanning_proof.py — Deterministic proof of dynamic tactical replanning.

Demonstrates under hostile scrutiny that:
1. Flood State A -> Plan A and Flood State B -> Plan B produce distinct tactical bypasses.
2. Tactical prescriptions evaluate the active damaged graph topology, not a static cache.
3. Evaluates hop radii k=1, 2, 3 to benchmark latency vs candidate count.
"""

import time
import pytest
import networkx as nx
from app.simulation.recommendations import generate_dynamic_prescriptions, get_cached_recommendations
from app.simulation.resilience import compute_resilience_index
from app.simulation.scenarios import ablate_nodes


def create_synthetic_grid(rows=6, cols=6):
    """Create a regular grid with realistic coordinates and travel times."""
    G = nx.grid_2d_graph(rows, cols)
    mapping = {}
    base_lat, base_lon = 12.93, 77.60
    for idx, (r, c) in enumerate(G.nodes()):
        node_id = f"node_{r}_{c}"
        mapping[(r, c)] = node_id
    G = nx.relabel_nodes(G, mapping)
    
    for n in G.nodes():
        parts = n.split("_")
        r, c = int(parts[1]), int(parts[2])
        G.nodes[n]["y"] = base_lat + r * 0.005
        G.nodes[n]["x"] = base_lon + c * 0.005
        G.nodes[n]["elevation"] = 890.0 + r * 1.0 + c * 0.5

    for u, v in G.edges():
        u_data, v_data = G.nodes[u], G.nodes[v]
        dist_m = 500.0
        G[u][v]["weight"] = dist_m
        G[u][v]["length"] = dist_m
        G[u][v]["time_s"] = dist_m / 10.0  # 10 m/s

    return G


class TestDynamicReplanningProof:

    def test_synthetic_grid_corridor_divergence(self):
        """Proof on controlled grid: cuts in North vs South corridors yield distinct bypasses."""
        G = create_synthetic_grid(6, 6)

        # Flood Corridor A (North: row 4)
        flooded_a = ["node_4_1", "node_4_2", "node_4_3"]
        G_alive_a = ablate_nodes(G, flooded_a)
        ri_a = compute_resilience_index(G, G_alive_a, sample_size=15)
        recs_a = generate_dynamic_prescriptions(G_alive_a, flooded_a, ri_a, G_full=G, hop_radius=2)

        # Flood Corridor B (South: row 1)
        flooded_b = ["node_1_2", "node_1_3", "node_1_4"]
        G_alive_b = ablate_nodes(G, flooded_b)
        ri_b = compute_resilience_index(G, G_alive_b, sample_size=15)
        recs_b = generate_dynamic_prescriptions(G_alive_b, flooded_b, ri_b, G_full=G, hop_radius=2)

        assert len(recs_a) > 0, "Plan A must produce recommendations"
        assert len(recs_b) > 0, "Plan B must produce recommendations"

        # Check targets
        targets_a = {rec["target_node"] for rec in recs_a}
        targets_b = {rec["target_node"] for rec in recs_b}

        # The target nodes for North cut must be in the North (row >= 3)
        for t in targets_a:
            row = int(t.split("_")[1])
            assert row >= 3, f"Target {t} in Plan A must be near North flood boundary"

        # The target nodes for South cut must be in the South (row <= 2)
        for t in targets_b:
            row = int(t.split("_")[1])
            assert row <= 2, f"Target {t} in Plan B must be near South flood boundary"

        # Plans must be strictly divergent
        assert targets_a != targets_b, "Plan A targets must differ from Plan B targets"
        assert recs_a[0]["target_nodes"] != recs_b[0]["target_nodes"]

    def test_empty_flood_returns_static_cache_safely(self):
        """When no nodes are flooded, system returns cached baseline without wasting compute."""
        G = create_synthetic_grid(5, 5)
        recs = generate_dynamic_prescriptions(G, [], {}, G_full=G)
        assert isinstance(recs, list)
        for r in recs:
            assert r.get("tactical_source") == "static_startup_cache"

    def test_hop_radius_scaling_benchmark(self):
        """Benchmark hop radius k=1, 2, 3 to prove SLA compliance and spatial scope."""
        G = create_synthetic_grid(6, 6)
        flooded = ["node_2_2", "node_2_3", "node_3_2", "node_3_3"]
        G_alive = ablate_nodes(G, flooded)
        ri = compute_resilience_index(G, G_alive, sample_size=10)

        timings = {}
        subgraph_sizes = {}
        for k in [1, 2, 3]:
            t0 = time.perf_counter()
            recs = generate_dynamic_prescriptions(G_alive, flooded, ri, G_full=G, hop_radius=k)
            elapsed = time.perf_counter() - t0
            timings[k] = elapsed
            subgraph_sizes[k] = recs[0].get("subgraph_nodes", 0) if recs else 0
            # SLA guard: all hop radii must execute in < 0.2s
            assert elapsed < 0.2, f"Hop radius {k} took {elapsed:.4f}s > 0.2s"

        # Higher hop radius yields equal or larger subgraph
        assert subgraph_sizes[2] >= subgraph_sizes[1]
        assert subgraph_sizes[3] >= subgraph_sizes[2]
