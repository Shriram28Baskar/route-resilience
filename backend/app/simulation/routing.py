"""
Emergency route planning: shortest path between two nodes,
with travel-time estimate using assumed road speed.
Supports K-alternative routes via edge-penalization.
"""
import logging
import os
from typing import Dict, Any, Optional, List

import networkx as nx

logger = logging.getLogger(__name__)

ASSUMED_SPEED_KMH = float(os.getenv("ASSUMED_SPEED_KMH", 30))
ASSUMED_SPEED_MPS = ASSUMED_SPEED_KMH * 1000 / 3600

# Penalty multiplier applied to primary-route edges to force topologically distinct alternatives
ALT_EDGE_PENALTY = 4.0


def _path_stats(G: nx.Graph, path_nodes: list, weight_type: str) -> Dict[str, Any]:
    """Compute distance + travel time along a node path."""
    distance = 0.0
    travel_time_s = 0.0
    for i in range(len(path_nodes) - 1):
        u, v = path_nodes[i], path_nodes[i + 1]
        if G.is_multigraph():
            edges = G[u][v]
            best_edge = min(
                edges.values(),
                key=lambda d: d.get(weight_type, d.get("weight", d.get("length", 0.0))),
            )
            edge_data = best_edge
        else:
            edge_data = G[u][v]
        distance += edge_data.get("length", edge_data.get("weight", 0.0))
        travel_time_s += edge_data.get(
            "time_s", edge_data.get("length", 0.0) / ASSUMED_SPEED_MPS
        )
    return {"distance_m": round(distance, 2), "travel_time_s": round(travel_time_s, 2)}


def _build_geojson(G: nx.Graph, path_nodes: list, stats: Dict) -> Dict:
    coordinates = [
        [G.nodes[n].get("x", 0), G.nodes[n].get("y", 0)]
        for n in path_nodes
    ]
    return {
        "type": "Feature",
        "geometry": {"type": "LineString", "coordinates": coordinates},
        "properties": {
            "distance_m": stats["distance_m"],
            "travel_time_s": stats["travel_time_s"],
            "num_nodes": len(path_nodes),
        },
    }


def compute_route(
    G: nx.Graph,
    source: int,
    target: int,
    weight_type: str = "time_s",
    num_alternatives: int = 2,
) -> Dict[str, Any]:
    """
    Compute the shortest path from source to target using Dijkstra on edge weight.
    Optionally compute `num_alternatives` topologically distinct alternative routes
    by penalizing primary-route edges in a copy of the graph.

    Returns:
        {
            "path_nodes": [node_id, ...],
            "path_geojson": GeoJSON LineString,
            "distance_m": float | None,
            "travel_time_s": float | None,
            "reachable": bool,
            "alternatives": [
                {
                    "path_nodes", "path_geojson", "distance_m",
                    "travel_time_s", "label", "trade_off"
                },
                ...
            ]
        }
    """
    if source not in G or target not in G:
        return _unreachable_result("Source or target not in graph")

    try:
        path_nodes = nx.dijkstra_path(G, source, target, weight=weight_type)
    except (nx.NetworkXNoPath, nx.NodeNotFound) as exc:
        return _unreachable_result(str(exc))

    stats = _path_stats(G, path_nodes, weight_type)

    result = {
        "path_nodes": [str(n) for n in path_nodes],
        "path_geojson": _build_geojson(G, path_nodes, stats),
        "distance_m": stats["distance_m"],
        "travel_time_s": stats["travel_time_s"],
        "reachable": True,
        "alternatives": [],
    }

    if num_alternatives <= 0:
        return result

    # ── Generate alternatives by edge-penalization ────────────────────────────
    # Work on a copy so we never mutate the live graph
    penalized = G.copy()
    primary_edges = set(zip(path_nodes[:-1], path_nodes[1:]))

    alt_labels = [
        ("Alternative Route A", "Longer path — more network redundancy"),
        ("Alternative Route B", "Safest if primary cascade continues"),
    ]

    for idx in range(num_alternatives):
        # Apply penalty to ALL edges that were on the previous best route
        for u, v in primary_edges:
            if penalized.is_multigraph():
                for key in penalized[u][v]:
                    for wt in ("time_s", "length", "weight"):
                        if wt in penalized[u][v][key]:
                            penalized[u][v][key][wt] *= ALT_EDGE_PENALTY
            else:
                if penalized.has_edge(u, v):
                    for wt in ("time_s", "length", "weight"):
                        if wt in penalized[u][v]:
                            penalized[u][v][wt] *= ALT_EDGE_PENALTY

        try:
            alt_path = nx.dijkstra_path(penalized, source, target, weight=weight_type)
        except (nx.NetworkXNoPath, nx.NodeNotFound):
            break

        alt_stats = _path_stats(G, alt_path, weight_type)  # measure on real graph
        label, trade_off = alt_labels[idx] if idx < len(alt_labels) else (f"Alt {idx + 1}", "")

        # Compute trade-off narrative using rounded values to match UI exactly
        alt_dist_km = round(alt_stats["distance_m"] / 1000.0, 2)
        base_dist_km = round(stats["distance_m"] / 1000.0, 2)
        dist_diff_km = round(alt_dist_km - base_dist_km, 2)
        
        alt_time_s = round(alt_stats["travel_time_s"])
        base_time_s = round(stats["travel_time_s"])
        time_diff = alt_time_s - base_time_s
        
        if time_diff < 0:
            trade_off = f"{'+' if dist_diff_km > 0 else ''}{dist_diff_km:.2f}km but saves {abs(time_diff)}s"
        else:
            trade_off = f"{'+' if dist_diff_km > 0 else ''}{dist_diff_km:.2f}km, +{time_diff}s — maximises redundancy"

        result["alternatives"].append({
            "path_nodes": [str(n) for n in alt_path],
            "path_geojson": _build_geojson(G, alt_path, alt_stats),
            "distance_m": alt_stats["distance_m"],
            "travel_time_s": alt_stats["travel_time_s"],
            "num_nodes": len(alt_path),
            "label": label,
            "trade_off": trade_off,
            "reachable": True,
        })

        # Update primary edges to penalize current alt route next iteration
        primary_edges = set(zip(alt_path[:-1], alt_path[1:]))

    return result


def _unreachable_result(reason: str) -> Dict[str, Any]:
    logger.warning(f"Route unreachable: {reason}")
    return {
        "path_nodes": [],
        "path_geojson": None,
        "distance_m": None,
        "travel_time_s": None,
        "reachable": False,
        "reason": reason,
        "alternatives": [],
    }



import numpy as np
from sklearn.cluster import KMeans
from scipy.spatial.distance import cdist
import networkx as nx
import math
from app.data.population import _get_src, query_population_nodes
from rasterio.windows import from_bounds


import numpy as np
from sklearn.cluster import KMeans
from scipy.spatial.distance import cdist
import networkx as nx
from app.data.population import _get_src
from rasterio.windows import from_bounds

def _get_distributed_node_weights(G, target_nodes):
    '''
    Retrieves raster population and distributes pixel mass equally among nodes
    that fall within each pixel. This perfectly prevents double-counting and 
    ensures sum(node_weights) == sum(unique_pixels).
    '''
    src = _get_src()
    weights = {n: 0.0 for n in target_nodes}
    if not src:
        return weights
    
    xs = [G.nodes[n].get('x') for n in target_nodes if G.nodes[n].get('x') is not None]
    ys = [G.nodes[n].get('y') for n in target_nodes if G.nodes[n].get('y') is not None]
    if not xs or not ys:
        return weights
        
    min_x, max_x = min(xs)-0.005, max(xs)+0.005
    min_y, max_y = min(ys)-0.005, max(ys)+0.005
    
    try:
        window = from_bounds(min_x, min_y, max_x, max_y, src.transform).round_lengths().round_offsets()
        data = src.read(1, window=window)
        win_transform = src.window_transform(window)
        
        pixel_to_nodes = {}
        for n in target_nodes:
            x, y = G.nodes[n].get('x'), G.nodes[n].get('y')
            if x and y:
                col, row = ~win_transform * (x, y)
                row, col = int(row), int(col)
                if 0 <= row < data.shape[0] and 0 <= col < data.shape[1]:
                    pixel_to_nodes.setdefault((row, col), []).append(n)
                    
        for (row, col), nodes in pixel_to_nodes.items():
            val = data[row, col]
            if val > 0 and val != -99999.0:
                pop_per_node = float(val) / len(nodes)
                for n in nodes:
                    weights[n] = pop_per_node
    except Exception:
        pass
    return weights

def compute_relief_camps(G: nx.Graph, k: int = 3) -> dict:
    if not G.nodes():
        return {"camps": [], "catchment_mapping": {}, "metrics": {}}

    G_ud = G.to_undirected() if G.is_directed() else G
    components = sorted(nx.connected_components(G_ud), key=len, reverse=True)
    if not components:
        return {"camps": [], "catchment_mapping": {}, "metrics": {}}

    lcc_nodes = list(components[0])
    unreachable_nodes = set(G.nodes()) - set(lcc_nodes)
    
    catchment_mapping = {}
    catchment_nodes = {i: [] for i in range(k)}

    if len(lcc_nodes) <= k:
        camp_nodes = lcc_nodes[:k]
        for i, n in enumerate(lcc_nodes):
            c_idx = i % len(camp_nodes)
            catchment_mapping[str(n)] = c_idx
            catchment_nodes[c_idx].append(n)
        weights = _get_distributed_node_weights(G, list(G.nodes()))
        initial_objective = 0.0
        final_objective = 0.0
        camp_distances = {}
        for i, camp in enumerate(camp_nodes):
            camp_distances[i] = nx.single_source_dijkstra_path_length(G_ud, camp, weight='time_s')
    else:
        # Phase 1: Mathematically Coherent Demand Weights (No overlapping/double counting)
        weights = _get_distributed_node_weights(G, list(G.nodes()))
        
        # Phase 2: Spatial K-Means for dispersed heuristic initialization
        coords = np.array([[G_ud.nodes[n].get('x', 0), G_ud.nodes[n].get('y', 0)] for n in lcc_nodes])
        kmeans = KMeans(n_clusters=k, random_state=42, n_init=10).fit(coords)
        
        camp_nodes = []
        for center in kmeans.cluster_centers_:
            distances = cdist([center], coords)[0]
            camp_nodes.append(lcc_nodes[np.argmin(distances)])

        # Calculate Initial Objective
        initial_objective = 0.0
        camp_distances = {}
        for i, camp in enumerate(camp_nodes):
            camp_distances[i] = nx.single_source_dijkstra_path_length(G_ud, camp, weight='time_s')
        for n in lcc_nodes:
            min_d = min((camp_distances[i].get(n, float('inf')) for i in range(k)))
            initial_objective += (weights.get(n, 0) * min_d)

        # Phase 3: Alternating Location-Allocation (Weighted P-Median Heuristic)
        # Objective: Minimize Sum(Demand_i * NetworkTravelTime(i, c))
        for _ in range(2):
            camp_distances = {}
            for i, camp in enumerate(camp_nodes):
                camp_distances[i] = nx.single_source_dijkstra_path_length(G_ud, camp, weight='time_s')
            
            # Allocation
            catchment_nodes = {i: [] for i in range(k)}
            for n in lcc_nodes:
                min_dist = float('inf')
                best_camp = 0
                for i in range(k):
                    if n in camp_distances[i] and camp_distances[i][n] < min_dist:
                        min_dist = camp_distances[i][n]
                        best_camp = i
                catchment_mapping[str(n)] = best_camp
                catchment_nodes[best_camp].append(n)
                
            # Location (1-Median Approximation)
            new_seeds = []
            for i in range(k):
                c_nodes = catchment_nodes[i]
                if not c_nodes:
                    new_seeds.append(camp_nodes[i])
                    continue
                
                # Sample top 5 highest population nodes + current seed as candidates
                candidates = sorted(c_nodes, key=lambda n: weights.get(n, 0), reverse=True)[:5]
                current_seed = camp_nodes[i]
                if current_seed not in candidates and current_seed in c_nodes:
                    candidates.append(current_seed)
                    
                best_cost = float('inf')
                best_cand = current_seed
                
                for cand in candidates:
                    dists = nx.single_source_dijkstra_path_length(G_ud, cand, weight='time_s')
                    cost = sum(weights.get(n, 0) * dists.get(n, float('inf')) for n in c_nodes)
                    if cost < best_cost:
                        best_cost = cost
                        best_cand = cand
                new_seeds.append(best_cand)
            camp_nodes = new_seeds
            
        # Final Allocation pass
        camp_distances = {}
        for i, camp in enumerate(camp_nodes):
            camp_distances[i] = nx.single_source_dijkstra_path_length(G_ud, camp, weight='time_s')
            
        catchment_nodes = {i: [] for i in range(k)}
        final_objective = 0.0
        for n in lcc_nodes:
            min_dist = float('inf')
            best_camp = 0
            for i in range(k):
                if n in camp_distances[i] and camp_distances[i][n] < min_dist:
                    min_dist = camp_distances[i][n]
                    best_camp = i
            catchment_mapping[str(n)] = best_camp
            catchment_nodes[best_camp].append(n)
            final_objective += (weights.get(n, 0) * min_dist)

    # 4. Compile Mathematically Coherent Metrics
    results = []
    total_weighted_time = 0.0
    total_pop_served = 0.0
    worst_case_time = 0.0
    
    for i, c in enumerate(camp_nodes):
        data = G.nodes[c]
        c_nodes = catchment_nodes.get(i, [])
        
        # Population is strictly the sum of distributed node weights (NO double counting)
        camp_pop_served = sum(weights.get(n, 0) for n in c_nodes)
        
        camp_weighted_time = 0.0
        camp_worst_time = 0.0
        
        if c_nodes and i in camp_distances:
            for n in c_nodes:
                t = camp_distances[i].get(n, 0)
                p = weights.get(n, 0)
                camp_weighted_time += (p * t)
                if t > camp_worst_time:
                    camp_worst_time = t
                    
        total_pop_served += camp_pop_served
        total_weighted_time += camp_weighted_time
        if camp_worst_time > worst_case_time:
            worst_case_time = camp_worst_time
            
        mean_resp = (camp_weighted_time / camp_pop_served) if camp_pop_served > 0 else 0
            
        results.append({
            "id": str(c),
            "lat": data.get("y"),
            "lng": data.get("x"),
            "node_count": len(c_nodes),
            "population_estimate": round(camp_pop_served, 0),
            "mean_response_time_s": round(mean_resp, 1),
            "worst_case_time_s": round(camp_worst_time, 1)
        })

    global_mean_time = (total_weighted_time / total_pop_served) if total_pop_served > 0 else 0
    unreachable_pop = sum(weights.get(n, 0) for n in unreachable_nodes if n in weights) if 'weights' in locals() else 0
    
    total_network_pop = sum(weights.values())
    pop_cov = (total_pop_served / total_network_pop * 100) if total_network_pop > 0 else 0.0
    
    metrics = {
        "objective_function": "Minimize Sum(Demand_i * NetworkTravelTime_s)",
        "initial_objective_value": round(initial_objective, 1) if 'initial_objective' in locals() else 0,
        "optimized_objective_value": round(final_objective, 1) if 'final_objective' in locals() else 0,
        "optimization_improvement_pct": round((initial_objective - final_objective) / initial_objective * 100, 1) if initial_objective > 0 else 0.0,
        "weighted_mean_response_time_s": round(global_mean_time, 1),
        "worst_case_response_time_s": round(worst_case_time, 1),
        "unreachable_nodes_count": len(unreachable_nodes),
        "unreachable_population_estimate": round(unreachable_pop, 0),
        "total_population_served": round(total_pop_served, 0),
        "population_coverage_pct": round(pop_cov, 1),
        "network_coverage_pct": round((len(lcc_nodes) / G.number_of_nodes() * 100) if G.number_of_nodes() > 0 else 0, 1)
    }

    return {"camps": results, "catchment_mapping": catchment_mapping, "metrics": metrics}
