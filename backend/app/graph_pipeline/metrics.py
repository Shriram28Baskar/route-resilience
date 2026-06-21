"""
Graph connectivity metrics and path-length computations.
"""
import logging
import weakref
from typing import Dict, Any, List

import networkx as nx

# Global weakref cache to avoid recalculating metrics for the same graph object.
_metrics_cache = weakref.WeakKeyDictionary()

logger = logging.getLogger(__name__)


def compute_graph_metrics(G: nx.Graph, fast: bool = False) -> Dict[str, Any]:
    """
    Compute a comprehensive set of network statistics for G.

    Returns a JSON-serializable dict with:
    - num_nodes, num_edges
    - num_components, largest_component_size
    - avg_node_degree
    - density
    - avg_shortest_path_length (on largest component, or None if trivial)
    - diameter (on largest component)
    """
    if G in _metrics_cache and not fast:
        logger.info(f"Returning cached metrics for graph {id(G)}")
        return _metrics_cache[G]

    if G.number_of_nodes() == 0:
        return _empty_metrics()

    components = list(nx.connected_components(G))
    lcc_nodes = max(components, key=len)
    lcc = G.subgraph(lcc_nodes)

    degrees = [d for _, d in G.degree()]
    avg_degree = sum(degrees) / len(degrees) if degrees else 0.0

    # Average shortest path length on LCC (expensive for large graphs)
    avg_path_length = None
    diameter = None
    if not fast and lcc.number_of_nodes() >= 2:
        try:
            if lcc.number_of_nodes() <= 1000:
                avg_path_length = nx.average_shortest_path_length(lcc, weight="weight")
                diameter = nx.diameter(lcc)
            else:
                # Approximate with a deterministic sample to prevent wild fluctuations
                import random
                sorted_nodes = sorted(list(lcc.nodes()))
                rand_gen = random.Random(42)
                sample = rand_gen.sample(sorted_nodes, min(300, len(sorted_nodes)))
                lengths = []
                for src in sample[:50]:
                    paths = nx.single_source_dijkstra_path_length(lcc, src, weight="weight")
                    lengths.extend([d for tgt, d in paths.items() if src != tgt])
                avg_path_length = sum(lengths) / len(lengths) if lengths else None
        except nx.NetworkXError as exc:
            logger.warning(f"Path length computation failed: {exc}")

    res = {
        "num_nodes": G.number_of_nodes(),
        "num_edges": G.number_of_edges(),
        "num_components": len(components),
        "largest_component_size": len(lcc_nodes),
        "largest_component_fraction": len(lcc_nodes) / G.number_of_nodes(),
        "avg_node_degree": round(avg_degree, 3),
        "density": round(nx.density(G), 6),
        "avg_shortest_path_length": round(avg_path_length, 4) if avg_path_length else None,
        "diameter": diameter,
    }
    if not fast:
        _metrics_cache[G] = res
    return res


def multi_source_shortest_paths(G: nx.Graph, source_nodes: List) -> Dict:
    """
    Compute shortest path distances from every node to its nearest source node.
    Used for hospital accessibility analysis.

    Returns dict: node_id -> {nearest_hospital_node: str, distance: float}
    """
    valid_sources = [s for s in source_nodes if s in G]
    if not valid_sources:
        return {}

    try:
        distances, paths = nx.multi_source_dijkstra(G, valid_sources, weight="weight")
        result = {
            node: {
                "nearest_hospital_node": str(paths[node][0]),
                "distance": dist,
            }
            for node, dist in distances.items()
        }
    except Exception as exc:
        logger.warning(f"Multi-source Dijkstra failed: {exc}")
        result = {}

    return result


def _empty_metrics() -> Dict[str, Any]:
    return {
        "num_nodes": 0,
        "num_edges": 0,
        "num_components": 0,
        "largest_component_size": 0,
        "largest_component_fraction": 0.0,
        "avg_node_degree": 0.0,
        "density": 0.0,
        "avg_shortest_path_length": None,
        "diameter": None,
    }
