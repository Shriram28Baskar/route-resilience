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
import threading
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

# Tactical optimisation is deliberately decoupled from the real-time disaster
# loop.  The source graph is static, so a snapshot produced during startup is
# valid for every observation cycle.  Copy on read prevents callers from
# mutating the cached decision input.
_CACHE_LOCK = threading.Lock()
_RECOMMENDATIONS_CACHE: List[Dict[str, Any]] | None = None


def cache_recommendations(recommendations: List[Dict[str, Any]]) -> None:
    """Publish a completed tactical optimisation snapshot without blocking readers."""
    global _RECOMMENDATIONS_CACHE
    with _CACHE_LOCK:
        _RECOMMENDATIONS_CACHE = [dict(recommendation) for recommendation in recommendations]


def get_cached_recommendations() -> List[Dict[str, Any]]:
    """Return the most recent completed tactical snapshot, or [] while warming up."""
    with _CACHE_LOCK:
        if _RECOMMENDATIONS_CACHE is None:
            return []
        return [dict(recommendation) for recommendation in _RECOMMENDATIONS_CACHE]


def recommendations_are_cached() -> bool:
    """Whether startup optimisation has published a completed snapshot."""
    with _CACHE_LOCK:
        return _RECOMMENDATIONS_CACHE is not None


def generate_dynamic_prescriptions(
    G_alive: nx.Graph,
    flooded_nodes: List,
    ri_result: dict,
    G_full: nx.Graph | None = None,
    hop_radius: int = 2,
    max_candidates: int = 6,
) -> List[Dict[str, Any]]:
    """Bounded tactical optimization on the live flood-constrained graph.

    Unlike generate_recommendations() (which runs on the static unflooded graph
    at startup), this function evaluates the CURRENT topology after flood ablation.
    It identifies which interventions remain meaningful given the active disaster
    state, so prescriptions change as flood extent changes.

    Algorithm
    ---------
    1. Identify the set of boundary nodes: neighbors of flooded nodes still in G_alive.
       These are the "pressure points" where adding redundancy has the most impact.
    2. Build a bounded subgraph: G_alive nodes within hop_radius of any boundary node.
       This constrains the search space to the tactically relevant region.
    3. Evaluate bypass-edge candidates within the bounded subgraph.
    4. Return up to _TOP_K prescriptions sorted by RI gain.

    Performance contract
    --------------------
    Bounded to max_candidates bypass evaluations on the bounded subgraph (<<< full graph).
    Typical runtime: < 0.05s.
    """
    if G_alive.number_of_nodes() < 10:
        return get_cached_recommendations()

    if not flooded_nodes:
        cached = get_cached_recommendations()
        for rec in cached:
            rec["tactical_source"] = "static_startup_cache"
        return cached

    flooded_set = set(flooded_nodes)

    # ── 1. Boundary nodes: G_alive nodes adjacent to flooded nodes ────────────
    if G_full is None:
        try:
            from app.graph_pipeline.graph_build import GraphStore
            G_full = GraphStore.get_osm_fallback()
        except Exception:
            G_full = None

    boundary_nodes: set = set()
    if G_full is not None:
        for fn in flooded_set:
            if fn in G_full:
                for nbr in G_full.neighbors(fn):
                    if nbr in G_alive:
                        boundary_nodes.add(nbr)

    # If boundary nodes cannot be derived, seed with highest-degree nodes in G_alive
    if not boundary_nodes:
        seed_nodes = {n for n, _ in sorted(G_alive.degree(), key=lambda x: x[1], reverse=True)[:max_candidates * 2]}
    else:
        # Prioritize boundary nodes with high degree
        sorted_boundary = sorted(boundary_nodes, key=lambda n: G_alive.degree(n), reverse=True)
        seed_nodes = set(sorted_boundary[:max_candidates * 3])

    # ── 2. Bounded subgraph: 2-hop BFS around flood boundary ──────────────────
    subgraph_nodes: set = set(seed_nodes)
    frontier = set(seed_nodes)
    for _ in range(hop_radius):
        next_frontier: set = set()
        for n in frontier:
            if n in G_alive:
                next_frontier.update(G_alive.neighbors(n))
        next_frontier -= subgraph_nodes
        subgraph_nodes.update(next_frontier)
        frontier = next_frontier
        if len(subgraph_nodes) > 250:
            break  # Strict SLA bounding

    G_sub = G_alive.subgraph(subgraph_nodes).copy()

    if G_sub.number_of_nodes() < 4:
        return get_cached_recommendations()

    try:
        centrality = compute_betweenness(G_sub, k=min(20, G_sub.number_of_nodes()))
        aps = set(get_articulation_points(G_sub))
    except Exception:
        return get_cached_recommendations()

    ranked_nodes = sorted(centrality.items(), key=lambda x: x[1], reverse=True)
    if not ranked_nodes:
        return get_cached_recommendations()

    # ── 3. Baseline RI on subgraph ────────────────────────────────────────────
    top_node = ranked_nodes[0][0] if ranked_nodes[0][0] in G_sub else next(
        (n for n, _ in ranked_nodes if n in G_sub), None
    )
    if top_node is None:
        return get_cached_recommendations()

    perturbed_sub = ablate_nodes(G_sub, [top_node])
    try:
        baseline_ri_info = compute_resilience_index(G_sub, perturbed_sub, sample_size=_RI_SAMPLE)
    except Exception:
        return get_cached_recommendations()

    baseline_ri = baseline_ri_info.get("resilience_index") or 0.0
    baseline_partitioned = baseline_ri_info.get("disconnected", False)

    # ── 4. Evaluate bypass candidates ────────────────────────────────────────
    recs: List[Dict[str, Any]] = []
    sub_ranked = [(n, centrality[n]) for n in G_sub.nodes() if n in centrality]
    sub_ranked.sort(key=lambda x: x[1], reverse=True)

    used_pairs: set = set()
    working_G = G_sub.copy()
    evaluated = 0

    for k_idx in range(_TOP_K):
        best_gain = -999.0
        best_rec: Dict[str, Any] | None = None
        best_G_after: nx.Graph | None = None

        for n1, _ in sub_ranked:
            if n1 not in working_G or evaluated >= max_candidates:
                break

            n1_data = working_G.nodes[n1]
            n1_lat = n1_data.get("y", 0.0)
            n1_lon = n1_data.get("x", 0.0)

            for n2, _ in sub_ranked:
                if n2 == n1 or n2 not in working_G:
                    continue
                if (n1, n2) in used_pairs or (n2, n1) in used_pairs:
                    continue
                if working_G.has_edge(n1, n2):
                    continue

                n2_data = working_G.nodes[n2]
                dist_m = _haversine_m(n1_lat, n1_lon, n2_data.get("y", 0.0), n2_data.get("x", 0.0))
                if dist_m > 8000:
                    continue

                G_test = working_G.copy()
                speed_kph = 50.0
                time_s = dist_m / (speed_kph * 1000 / 3600)
                G_test.add_edge(n1, n2, weight=dist_m, length=dist_m, speed_kph=speed_kph, time_s=time_s)

                gain = _ri_gain(working_G, G_test, top_node, baseline_ri)
                evaluated += 1
                n1_is_ap = n1 in aps

                if gain > best_gain:
                    best_gain = gain
                    best_rec = {
                        "type": "bypass",
                        "title": "Emergency Bypass Corridor" if dist_m > 200 else "Tactical Bridge",
                        "description": (
                            f"Flood-state bypass: {dist_m:.0f}m link connecting #{n1}↔#{n2}. "
                            f"Node #{n1} is {'an articulation point controlling' if n1_is_ap else 'a high-flow node handling'} "
                            f"~{centrality.get(n1, 0)*100:.1f}% of surviving paths. "
                            f"Evaluated against live flood topology (seq={ri_result.get('sample_size','?')} RI samples)."
                        ),
                        "target_nodes": [str(n1), str(n2)],
                        "target_node": str(n1),
                        # M6 (removed): max(gain, 0.001) floored every recommendation to a
                        # positive gain. Measured value reported as-is.
                        "rgs": round(gain, 6),
                        "ri_before": round(baseline_ri, 4),
                        "ri_after": round(baseline_ri + gain, 4),
                        "is_articulation_point": n1_is_ap,
                        # M8 (removed): protects_residents was nodes x betweenness x 50.
                        # Betweenness is a path count, not people, and no census
                        # layer is joined anywhere. No substitute is supplied.
                        "protects_residents": None,
                        "cascade_prevention": baseline_partitioned,
                        "bypass_length_m": round(dist_m, 0),
                        # M8 (removed): _cost_estimate() is an unsourced rupee literal keyed
                        # on length. No costing model exists.
                        "cost_estimate": None,
                        "action": "new_road",
                        "tactical_source": "dynamic_bounded_subgraph",
                        "subgraph_nodes": G_sub.number_of_nodes(),
                        "hop_radius": hop_radius,
                    }
                    best_G_after = G_test
                    best_pair = (n1, n2)

                break  # one partner per candidate to stay fast

        if best_rec is not None:
            recs.append(best_rec)
            working_G = best_G_after
            used_pairs.add(best_pair)
        else:
            break

    if not recs:
        # No improvement found in the bounded subgraph — fall back to cached static recs
        # but annotate them so the consumer knows they're not flood-topology-aware
        cached = get_cached_recommendations()
        for rec in cached:
            rec["tactical_source"] = "static_startup_cache"
        return cached

    # Recommendations with no measurable or a negative gain stay in the list:
    # suppressing them would reintroduce "every recommendation helps".
    recs.sort(key=lambda x: (x["rgs"] is None, -(x["rgs"] or 0.0)))
    return recs


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
                    # M8 (removed): fabricated population estimate; no census join exists.
                    protected_pop = None
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
                        # M6 (removed): max(gain, 0.001) floored every recommendation to a
                        # positive gain. Measured value reported as-is.
                        "rgs": round(gain, 6),
                        "ri_before": round(baseline_ri, 4),
                        "ri_after": round(baseline_ri + gain, 4),
                        "is_articulation_point": n1_is_ap,
                        "protects_residents": protected_pop,
                        "cascade_prevention": baseline_partitioned,
                        "bypass_length_m": round(dist_m, 0),
                        # M8 (removed): _cost_estimate() is an unsourced rupee literal keyed
                        # on length. No costing model exists.
                        "cost_estimate": None,
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
            # M5 (removed): max(rgs, 0.05) floored every reinforcement rec.
            "rgs": round(rgs, 4),
            "rgs_definition": ("1 - RI(baseline with this node ablated); the damage "
                               "averted IF hardening fully prevents failure"),
            "ri_before": round(baseline_ri, 4),
            # M7 (removed): ri_after was `min(1.0, baseline_ri + rgs * 0.5)`. The
            # 0.5 coefficient was invented and the value was never obtained by
            # running the intervention. Hardening is not simulated here, so no
            # post-intervention index is reported.
            "ri_after": None,
            "is_articulation_point": top_n in aps,
            "protects_residents": None,   # M8 (removed): fabricated
            "cascade_prevention": baseline_partitioned,
            "bypass_length_m": 0,
            "cost_estimate": None,   # M8 (removed): unsourced
            "action": "flood_barrier",
        })

    # Recommendations with no measurable or a negative gain stay in the list:
    # suppressing them would reintroduce "every recommendation helps".
    recs.sort(key=lambda x: (x["rgs"] is None, -(x["rgs"] or 0.0)))
    return recs
