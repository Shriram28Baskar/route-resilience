"""
Betweenness centrality computation for road graphs.
Uses k-sample approximation for large graphs to stay within time budget.
"""
import logging
import weakref
import pickle
import os
from typing import Dict, Optional

import networkx as nx

# Global weakref cache to avoid recalculating centrality for the same graph object.
# Maps G -> { metric_name: metric_data }
_centrality_cache = weakref.WeakKeyDictionary()


logger = logging.getLogger(__name__)

DEFAULT_K = 50   # number of pivot nodes for approximation
CRITICALITY_CACHE_PATH = "data/graphs/osm_fallback_criticality.pickle"


def _load_osm_fallback_criticality_cache() -> dict:
    if os.path.exists(CRITICALITY_CACHE_PATH):
        try:
            with open(CRITICALITY_CACHE_PATH, "rb") as f:
                return pickle.load(f)
        except Exception as exc:
            logger.warning(f"Failed to load criticality cache from {CRITICALITY_CACHE_PATH}: {exc}")
    return {}


def _save_osm_fallback_criticality_cache(cache_dict: dict):
    try:
        os.makedirs(os.path.dirname(CRITICALITY_CACHE_PATH), exist_ok=True)
        with open(CRITICALITY_CACHE_PATH, "wb") as f:
            pickle.dump(cache_dict, f)
        logger.info(f"Saved criticality cache to {CRITICALITY_CACHE_PATH}")
    except Exception as exc:
        logger.warning(f"Failed to save criticality cache to {CRITICALITY_CACHE_PATH}: {exc}")


def compute_betweenness(G: nx.Graph, k: Optional[int] = DEFAULT_K) -> Dict[int, float]:
    """
    Compute weighted betweenness centrality for all nodes.

    Uses Brandes' algorithm with k-sampling for large graphs.
    Normalizes scores to [0, 1] range for consistent frontend coloring.

    Args:
        G: NetworkX graph with edge attribute 'weight' (road length).
        k: Number of pivot nodes to sample. None = exact (expensive for large graphs).

    Returns:
        Dict mapping node ID → normalized centrality score in [0, 1].
    """
    n = G.number_of_nodes()
    if n == 0:
        return {}

    if G.graph.get("is_osm_fallback"):
        disk_cache = _load_osm_fallback_criticality_cache()
        if "betweenness" in disk_cache:
            logger.info("Returning disk-cached betweenness centrality for OSM fallback graph")
            return disk_cache["betweenness"]

    # Use exact algorithm for small graphs
    effective_k = None if n <= 500 else min(k or DEFAULT_K, n)

    if G not in _centrality_cache:
        _centrality_cache[G] = {}

    cache_key = f"betweenness_k{effective_k}"
    if cache_key in _centrality_cache[G]:
        logger.info(f"Returning cached centrality for graph {id(G)} with k={effective_k or 'exact'}")
        return _centrality_cache[G][cache_key]

    logger.info(f"Computing betweenness centrality: {n} nodes, k={effective_k or 'exact'}")

    # Work on the largest connected component to avoid infinity issues
    lcc = _largest_connected_component(G)

    try:
        centrality = nx.betweenness_centrality(
            lcc,
            k=effective_k,
            normalized=True,
            weight="weight",
            seed=42,
        )
    except Exception as exc:
        logger.warning(f"Betweenness centrality failed: {exc}. Returning uniform scores.")
        return {n: 0.0 for n in G.nodes()}

    # Fill in nodes not in LCC with score 0
    all_centrality = {node: 0.0 for node in G.nodes()}
    all_centrality.update(centrality)

    # Re-normalize across full graph
    max_score = max(all_centrality.values(), default=1.0)
    if max_score > 0:
        all_centrality = {k: v / max_score for k, v in all_centrality.items()}

    logger.info(f"Centrality computed. Max={max_score:.6f}, "
                f"Top node: {max(all_centrality, key=all_centrality.get)}")
    
    _centrality_cache[G][cache_key] = all_centrality

    if G.graph.get("is_osm_fallback"):
        disk_cache = _load_osm_fallback_criticality_cache()
        disk_cache["betweenness"] = all_centrality
        _save_osm_fallback_criticality_cache(disk_cache)

    return all_centrality

def compute_closeness(G: nx.Graph, k: Optional[int] = 50) -> Dict[int, float]:
    """
    Compute closeness centrality for all nodes.
    Higher values mean the node is closer to all other nodes.
    Uses k-sample approximation for large graphs to run in milliseconds.
    """
    if G not in _centrality_cache:
        _centrality_cache[G] = {}
        
    cache_key = f"closeness_k{k}"
    if cache_key in _centrality_cache[G]:
        return _centrality_cache[G][cache_key]

    if G.graph.get("is_osm_fallback"):
        disk_cache = _load_osm_fallback_criticality_cache()
        if "closeness" in disk_cache:
            logger.info("Returning disk-cached closeness centrality for OSM fallback graph")
            return disk_cache["closeness"]
        
    logger.info(f"Computing closeness centrality (k={k})...")
    lcc = _largest_connected_component(G)
    n = lcc.number_of_nodes()
    
    if n == 0:
        return {}
        
    try:
        if n <= 500:
            centrality = nx.closeness_centrality(lcc, distance="weight")
        else:
            import random
            sample_nodes = random.sample(list(lcc.nodes()), min(k or 50, n))
            dist_sums = {node: 0.0 for node in lcc.nodes()}
            reachable_counts = {node: 0 for node in lcc.nodes()}
            
            for src in sample_nodes:
                paths = nx.single_source_dijkstra_path_length(lcc, src, weight="weight")
                for node, dist in paths.items():
                    dist_sums[node] += dist
                    reachable_counts[node] += 1
            
            centrality = {}
            for node in lcc.nodes():
                if dist_sums[node] > 0 and reachable_counts[node] > 0:
                    centrality[node] = (reachable_counts[node] - 1) / dist_sums[node] if reachable_counts[node] > 1 else 0.0
                else:
                    centrality[node] = 0.0
    except Exception as exc:
        logger.warning(f"Closeness centrality failed: {exc}")
        return {n: 0.0 for n in G.nodes()}
        
    all_centrality = {node: 0.0 for node in G.nodes()}
    all_centrality.update(centrality)
    
    max_score = max(all_centrality.values(), default=1.0)
    if max_score > 0:
        all_centrality = {k: v / max_score for k, v in all_centrality.items()}
        
    _centrality_cache[G][cache_key] = all_centrality

    if G.graph.get("is_osm_fallback"):
        disk_cache = _load_osm_fallback_criticality_cache()
        disk_cache["closeness"] = all_centrality
        _save_osm_fallback_criticality_cache(disk_cache)

    return all_centrality

def get_articulation_points(G: nx.Graph) -> list:
    """
    Identify articulation points (nodes whose removal increases the number of connected components).
    """
    if G not in _centrality_cache:
        _centrality_cache[G] = {}
        
    cache_key = "articulation_points"
    if cache_key in _centrality_cache[G]:
        return _centrality_cache[G][cache_key]

    if G.graph.get("is_osm_fallback"):
        disk_cache = _load_osm_fallback_criticality_cache()
        if "articulation_points" in disk_cache:
            logger.info("Returning disk-cached articulation points for OSM fallback graph")
            return disk_cache["articulation_points"]
        
    logger.info("Finding articulation points...")
    ap = list(nx.articulation_points(G))
    _centrality_cache[G][cache_key] = ap

    if G.graph.get("is_osm_fallback"):
        disk_cache = _load_osm_fallback_criticality_cache()
        disk_cache["articulation_points"] = ap
        _save_osm_fallback_criticality_cache(disk_cache)

    return ap

def compute_edge_betweenness(G: nx.Graph, k: Optional[int] = DEFAULT_K) -> Dict[tuple, float]:
    """
    Compute edge betweenness centrality (fraction of shortest paths passing through each edge).
    """
    n = G.number_of_nodes()
    if n == 0:
        return {}
        
    effective_k = None if n <= 500 else min(k or DEFAULT_K, n)
    
    if G not in _centrality_cache:
        _centrality_cache[G] = {}
        
    cache_key = f"edge_betweenness_k{effective_k}"
    if cache_key in _centrality_cache[G]:
        return _centrality_cache[G][cache_key]

    if G.graph.get("is_osm_fallback"):
        disk_cache = _load_osm_fallback_criticality_cache()
        if "edge_betweenness" in disk_cache:
            logger.info("Returning disk-cached edge betweenness for OSM fallback graph")
            return disk_cache["edge_betweenness"]
        
    logger.info(f"Computing edge betweenness, k={effective_k or 'exact'}")
    lcc = _largest_connected_component(G)
    
    try:
        centrality = nx.edge_betweenness_centrality(lcc, k=effective_k, weight="weight", seed=42)
    except Exception as exc:
        logger.warning(f"Edge betweenness failed: {exc}")
        return {}
        
    # Re-normalize
    max_score = max(centrality.values(), default=1.0)
    if max_score > 0:
        centrality = {k: v / max_score for k, v in centrality.items()}
        
    _centrality_cache[G][cache_key] = centrality

    if G.graph.get("is_osm_fallback"):
        disk_cache = _load_osm_fallback_criticality_cache()
        disk_cache["edge_betweenness"] = centrality
        _save_osm_fallback_criticality_cache(disk_cache)

    return centrality


def _largest_connected_component(G: nx.Graph) -> nx.Graph:
    """Return the subgraph corresponding to the largest connected component."""
    if nx.is_connected(G):
        return G
    lcc_nodes = max(nx.connected_components(G), key=len)
    return G.subgraph(lcc_nodes).copy()


def get_gatekeepers(G: nx.Graph, top_n: int = 10, k: Optional[int] = DEFAULT_K) -> list:
    """
    Return the top_n nodes by betweenness centrality as a sorted list of dicts.
    """
    centrality = compute_betweenness(G, k=k)
    ranked = sorted(centrality.items(), key=lambda x: x[1], reverse=True)
    return [
        {
            "node_id": nid,
            "centrality": score,
            "x": G.nodes[nid].get("x", 0),
            "y": G.nodes[nid].get("y", 0),
        }
        for nid, score in ranked[:top_n]
    ]
