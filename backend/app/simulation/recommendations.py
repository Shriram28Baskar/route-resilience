"""
Infrastructure Recommendation Engine — Greedy Resilience Optimizer

Uses a greedy argmax approach to identify the K highest-ROI interventions:
  1. Identify all articulation points (structurally critical nodes).
  2. For each AP, simulate hardening it (bypass: add redundant edge; reinforce: flag as protected).
  3. Measure the Resilience Index gain each intervention provides.
  4. Return the top K, sorted by RI gain descending.

Complexity: O(K × |AP| × RI_sample) — fast due to cached RI baseline and sampled Dijkstra.
"""
import logging
import math
import networkx as nx
from typing import List, Dict, Any

from app.graph_pipeline.centrality import compute_betweenness, get_articulation_points
from app.simulation.resilience import compute_resilience_index
from app.simulation.ablation import ablate_nodes

logger = logging.getLogger(__name__)

# Number of recommendations to generate
_TOP_K = 3
# Sample size for RI computation during optimization.
# 20 sources is still statistically robust for a 13k-node graph (was 40 — halved for speed)
_RI_SAMPLE = 20


def _haversine_m(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Haversine distance in meters."""
    R = 6_371_000.0
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = math.sin(dlat / 2) ** 2 + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.sin(dlon / 2) ** 2
    return R * 2 * math.asin(math.sqrt(max(0.0, a)))


def _cost_estimate(dist_m: float, road_type: str = "bypass") -> str:
    """Rough construction cost estimate based on bypass length."""
    if dist_m < 500:
        return "Low — requires 1 road bridge or bypass"
    elif dist_m < 1500:
        return "Medium — requires 1 road bridge or bypass"
    else:
        return "High — major corridor construction"


def _ri_gain(
    G_original: nx.Graph,
    G_modified: nx.Graph,
    top_node,
    ri_original_val: float,
) -> float:
    """
    Compute RI improvement from a graph modification.

    Accepts precomputed top_node and ri_original_val to avoid recomputing
    betweenness centrality and the original RI on every candidate evaluation.
    Only computes RI for the modified graph (1 RI computation per call, was 2).
    """
    if top_node is None:
        return 0.0

    perturbed_modified = ablate_nodes(G_modified, [top_node])
    ri_modified = compute_resilience_index(G_modified, perturbed_modified, sample_size=_RI_SAMPLE)
    ri_mod_val = ri_modified.get("resilience_index") or 0.0

    return round(ri_mod_val - ri_original_val, 4)


def generate_recommendations(G: nx.Graph) -> List[Dict[str, Any]]:
    """
    Greedy argmax: find the TOP_K interventions with the highest RI gain.

    Each iteration:
      - Scores all candidate articulation points as bypass targets.
      - Picks the best one.
      - Applies it to the working graph for the next iteration (greedy composition).

    Returns recommendations sorted by Resilience Gain Score (RGS) descending.
    """
    recs: List[Dict[str, Any]] = []

    # ── 1. Baseline metrics ──────────────────────────────────────────────────
    centrality = compute_betweenness(G, k=50)
    aps = set(get_articulation_points(G))
    ranked_nodes = sorted(centrality.items(), key=lambda x: x[1], reverse=True)

    if not ranked_nodes:
        return []

    # Baseline RI: how resilient is the network right now?
    top_node = ranked_nodes[0][0]
    perturbed_baseline = ablate_nodes(G, [top_node])
    baseline_ri_info = compute_resilience_index(G, perturbed_baseline, sample_size=_RI_SAMPLE)
    baseline_ri = baseline_ri_info.get("resilience_index") or 0.0
    baseline_partitioned = baseline_ri_info.get("disconnected", False)
    baseline_partitions = baseline_ri_info.get("partition_count", 1)

    logger.info(f"Baseline RI after top-node failure: {baseline_ri:.4f}, disconnected={baseline_partitioned}")

    # ── 2. Candidate nodes: APs + top betweenness nodes ─────────────────────
    # Prioritize articulation points (structural single points of failure)
    # then fill with top betweenness nodes if we don't have enough APs
    ap_ranked = [n for n, _ in ranked_nodes if n in aps]
    non_ap_ranked = [n for n, _ in ranked_nodes if n not in aps]
    candidates = (ap_ranked + non_ap_ranked)[:min(15, len(ranked_nodes))]

    working_G = G.copy()
    used_pairs: set = set()

    for k_idx in range(_TOP_K):
        best_gain = -999.0
        best_rec: Dict[str, Any] | None = None
        best_G_after: nx.Graph | None = None

        for i, n1 in enumerate(candidates):
            if n1 not in working_G:
                continue

            # Find nearest high-betweenness neighbor to build bypass
            n1_data = working_G.nodes[n1]
            n1_lat = n1_data.get("y", 0.0)
            n1_lon = n1_data.get("x", 0.0)

            # Score top candidates as bypass partners
            for n2, _ in ranked_nodes:
                if n2 == n1 or n2 not in working_G:
                    continue
                if (n1, n2) in used_pairs or (n2, n1) in used_pairs:
                    continue
                if working_G.has_edge(n1, n2):
                    continue

                n2_data = working_G.nodes[n2]
                dist_m = _haversine_m(n1_lat, n1_lon, n2_data.get("y", 0.0), n2_data.get("x", 0.0))

                # Only propose bypasses that are physically plausible (< 8 km)
                if dist_m > 8000:
                    continue

                # Simulate adding this bypass edge
                G_test = working_G.copy()
                speed_kph = 50.0
                time_s = dist_m / (speed_kph * 1000 / 3600)
                G_test.add_edge(n1, n2, weight=dist_m, length=dist_m, speed_kph=speed_kph, time_s=time_s)

                gain = _ri_gain(working_G, G_test, top_node, baseline_ri)
                if gain > best_gain:
                    best_gain = gain
                    n1_is_ap = n1 in aps
                    n2_is_ap = n2 in aps
                    protected_pop = int(G.number_of_nodes() * centrality.get(n1, 0) * 50)  # rough estimate
                    best_rec = {
                        "type": "bypass",
                        "title": "Pre-Build Road Bridge" if dist_m < 200 else "Construct Bypass Corridor",
                        "description": (
                            f"A new {dist_m:.0f}m bypass connecting critical junctions #{n1} and #{n2}. "
                            f"Node #{n1} is {'an articulation point controlling' if n1_is_ap else 'a high-betweenness node influencing'} "
                            f"~{centrality.get(n1, 0)*100:.1f}% of shortest paths."
                        ),
                        "target_nodes": [str(n1), str(n2)],
                        "target_node": str(n1),
                        "rgs": max(gain, 0.001),
                        "ri_before": round(baseline_ri, 4),
                        "ri_after": round(baseline_ri + gain, 4),
                        "is_articulation_point": n1_is_ap,
                        "protects_residents": protected_pop,
                        "cascade_prevention": baseline_partitioned,
                        "bypass_length_m": round(dist_m, 0),
                        "cost_estimate": _cost_estimate(dist_m),
                        "action": "new_road",
                    }
                    best_G_after = G_test
                    best_pair = (n1, n2)

                break  # Only test closest viable partner per candidate to keep it fast

        if best_rec is not None:
            recs.append(best_rec)
            working_G = best_G_after
            used_pairs.add(best_pair)
            logger.info(f"Recommendation {k_idx + 1}: RI gain={best_gain:.4f} ({best_rec['title']})")
        else:
            logger.info(f"No more improvement found at iteration {k_idx + 1}.")
            break

    # ── 3. If we still have fewer than TOP_K, add a reinforcement rec ───────
    if len(recs) < _TOP_K and ranked_nodes:
        top_n = ranked_nodes[0][0]
        # Reuse already-computed baseline_ri_info (top_node == top_n by construction above)
        rgs = 1.0 - baseline_ri
        recs.append({
            "type": "reinforcement",
            "title": f"Harden Gatekeeper Intersection #{top_n}",
            "description": (
                f"This node controls {centrality.get(top_n, 0)*100:.1f}% of all shortest paths. "
                "Installing flood barriers and structural reinforcement prevents cascading failures."
            ),
            "target_node": str(top_n),
            "target_nodes": [str(top_n)],
            "rgs": round(max(rgs, 0.05), 4),
            "ri_before": round(baseline_ri, 4),
            "ri_after": round(min(1.0, baseline_ri + rgs * 0.5), 4),
            "is_articulation_point": top_n in aps,
            "protects_residents": int(G.number_of_nodes() * centrality.get(top_n, 0) * 50),
            "cascade_prevention": baseline_partitioned,
            "bypass_length_m": 0,
            "cost_estimate": "Medium — flood barrier + structural reinforcement",
            "action": "flood_barrier",
        })

    recs.sort(key=lambda x: x["rgs"], reverse=True)
    return recs

