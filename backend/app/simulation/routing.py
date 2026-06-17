"""
Emergency route planning: shortest path between two nodes,
with travel-time estimate using assumed road speed.
"""
import logging
import os
from typing import Dict, Any, Optional

import networkx as nx

logger = logging.getLogger(__name__)

ASSUMED_SPEED_KMH = float(os.getenv("ASSUMED_SPEED_KMH", 30))
ASSUMED_SPEED_MPS = ASSUMED_SPEED_KMH * 1000 / 3600


def compute_route(
    G: nx.Graph,
    source: int,
    target: int,
    weight_type: str = "time_s",
) -> Dict[str, Any]:
    """
    Compute the shortest path from source to target using Dijkstra on edge weight.

    Returns:
        {
            "path_nodes": [node_id, ...],
            "path_geojson": GeoJSON LineString,
            "distance_m": float | None,
            "travel_time_s": float | None,
            "reachable": bool,
        }
    """
    if source not in G or target not in G:
        return _unreachable_result("Source or target not in graph")

    try:
        path_nodes = nx.dijkstra_path(G, source, target, weight=weight_type)
        # Sum up distance and travel time along the path edges
        distance = 0.0
        travel_time_s = 0.0
        for i in range(len(path_nodes) - 1):
            u, v = path_nodes[i], path_nodes[i+1]
            if G.is_multigraph():
                edges = G[u][v]
                # Select the edge with the minimum weight according to the routing weight_type
                best_edge = min(edges.values(), key=lambda d: d.get(weight_type, d.get("weight", d.get("length", 0.0))))
                edge_data = best_edge
            else:
                edge_data = G[u][v]
            distance += edge_data.get("length", edge_data.get("weight", 0.0))
            travel_time_s += edge_data.get("time_s", edge_data.get("length", 0.0) / ASSUMED_SPEED_MPS)
    except nx.NetworkXNoPath:
        return _unreachable_result("No path exists between source and target (graph may be disconnected)")
    except nx.NodeNotFound as exc:
        return _unreachable_result(str(exc))

    # Build GeoJSON LineString from path node coordinates
    coordinates = [
        [G.nodes[n].get("x", 0), G.nodes[n].get("y", 0)]
        for n in path_nodes
    ]

    return {
        "path_nodes": [str(n) for n in path_nodes],
        "path_geojson": {
            "type": "Feature",
            "geometry": {"type": "LineString", "coordinates": coordinates},
            "properties": {
                "distance_m": round(distance, 2),
                "travel_time_s": round(travel_time_s, 2),
                "num_nodes": len(path_nodes),
            },
        },
        "distance_m": round(distance, 2),
        "travel_time_s": round(travel_time_s, 2),
        "reachable": True,
    }


def _unreachable_result(reason: str) -> Dict[str, Any]:
    logger.warning(f"Route unreachable: {reason}")
    return {
        "path_nodes": [],
        "path_geojson": None,
        "distance_m": None,
        "travel_time_s": None,
        "reachable": False,
        "reason": reason,
    }


def compute_relief_camps(G: nx.Graph, k: int = 3) -> list:
    """
    Greedy K-Center algorithm to find k optimal relief camp locations.
    Minimizes the maximum travel distance to any node in the largest connected component.
    """
    if not G.nodes():
        return []
        
    if G.is_directed():
        G_ud = G.to_undirected()
    else:
        G_ud = G
        
    # We must place camps in the largest component to actually reach people
    components = sorted(nx.connected_components(G_ud), key=len, reverse=True)
    if not components:
        return []
        
    lcc_nodes = list(components[0])
    
    if len(lcc_nodes) <= k:
        camps = lcc_nodes[:k]
    else:
        # Start with the node that has highest degree as a good central heuristic
        start_node = max(lcc_nodes, key=lambda n: G_ud.degree(n))
        camps = [start_node]
        
        for _ in range(k - 1):
            distances = nx.multi_source_dijkstra_path_length(G_ud, camps, weight="length")
            
            max_dist = -1
            best_camp = None
            
            for n in lcc_nodes:
                d = distances.get(n, float('inf'))
                if d > max_dist and d != float('inf'):
                    max_dist = d
                    best_camp = n
                    
            if best_camp:
                camps.append(best_camp)
                
    results = []
    for c in camps:
        data = G.nodes[c]
        results.append({
            "id": str(c),
            "lat": data.get("y"),
            "lng": data.get("x")
        })
        
    return results
