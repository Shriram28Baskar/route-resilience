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


def compute_relief_camps(G: nx.Graph, k: int = 3) -> dict:
    """
    Finds k optimal relief camp locations by clustering the largest connected component.
    Uses K-Means clustering to minimize average travel distance to camps, avoiding edge placement.
    Returns both the camp locations and a catchment_mapping (node_id -> cluster_index) for
    rendering color-coded catchment zones on the map.
    """
    import numpy as np
    from sklearn.cluster import KMeans
    from scipy.spatial.distance import cdist
    if not G.nodes():
        return {"camps": [], "catchment_mapping": {}}

    if G.is_directed():
        G_ud = G.to_undirected()
    else:
        G_ud = G

    components = sorted(nx.connected_components(G_ud), key=len, reverse=True)
    if not components:
        return {"camps": [], "catchment_mapping": {}}

    lcc_nodes = list(components[0])

    catchment_mapping = {}  # node_id (str) -> cluster index (int)

    if len(lcc_nodes) <= k:
        camp_nodes = lcc_nodes[:k]
        # Every node gets assigned to its nearest camp by index
        for i, n in enumerate(lcc_nodes):
            catchment_mapping[str(n)] = i % len(camp_nodes)
    else:
        coords = np.array([[G_ud.nodes[n].get('x', 0), G_ud.nodes[n].get('y', 0)] for n in lcc_nodes])
        kmeans = KMeans(n_clusters=k, random_state=42, n_init=10).fit(coords)
        labels = kmeans.labels_
        centers = kmeans.cluster_centers_

        # Build catchment mapping from KMeans labels
        for i, n in enumerate(lcc_nodes):
            catchment_mapping[str(n)] = int(labels[i])

        camp_nodes = []
        for center in centers:
            distances = cdist([center], coords)[0]
            closest_idx = np.argmin(distances)
            camp_nodes.append(lcc_nodes[closest_idx])

    results = []
    for c in camp_nodes:
        data = G.nodes[c]
        results.append({"id": str(c), "lat": data.get("y"), "lng": data.get("x")})

    # Build per-camp population counts (nodes in each catchment)
    camp_counts = {}
    for node_id, cluster_idx in catchment_mapping.items():
        camp_counts[cluster_idx] = camp_counts.get(cluster_idx, 0) + 1

    for i, camp in enumerate(results):
        camp["node_count"] = camp_counts.get(i, 0)
        camp["population_estimate"] = camp_counts.get(i, 0) * 1008

    return {"camps": results, "catchment_mapping": catchment_mapping}
