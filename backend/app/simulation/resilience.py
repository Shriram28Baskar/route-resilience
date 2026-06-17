"""
Resilience Index: R = avg_shortest_path(baseline) / avg_shortest_path(perturbed)

R < 1  → paths longer after ablation (network degraded)
R = 1  → no change (resilient)
R > 1  → paths shorter (shouldn't happen unless graph is partitioned and
          we report LCC metrics only)
"""
import logging
from typing import Dict, Any, Optional

import networkx as nx

logger = logging.getLogger(__name__)

ASSUMED_SPEED_MPS = 30_000 / 3600   # 30 km/h → m/s


def compute_resilience_index(
    baseline_G: nx.Graph,
    perturbed_G: nx.Graph,
    sample_size: int = 200,
) -> Dict[str, Any]:
    """
    Compute the Resilience Index between a baseline and a perturbed graph.

    Uses approximate average shortest path length (sampled Dijkstra) for
    performance on large graphs.

    Returns:
        {
            "resilience_index": float | None,
            "baseline_avg_path": float | None,
            "perturbed_avg_path": float | None,
            "disconnected": bool,          # True if perturbed graph is disconnected
            "partition_count": int,        # number of components in perturbed graph
        }
    """
    baseline_avg = _sample_avg_path(baseline_G, sample_size)
    perturbed_avg = _sample_avg_path(perturbed_G, sample_size)

    is_disconnected = not nx.is_connected(perturbed_G)
    partition_count = nx.number_connected_components(perturbed_G)

    if baseline_avg is not None and perturbed_avg is not None and perturbed_avg > 0:
        ri = baseline_avg / perturbed_avg
    else:
        ri = None

    logger.info(f"Resilience Index: R={ri}, baseline={baseline_avg}, perturbed={perturbed_avg}, "
                f"disconnected={is_disconnected}")

    return {
        "resilience_index": round(ri, 4) if ri is not None else None,
        "baseline_avg_path": round(baseline_avg, 4) if baseline_avg is not None else None,
        "perturbed_avg_path": round(perturbed_avg, 4) if perturbed_avg is not None else None,
        "disconnected": is_disconnected,
        "partition_count": partition_count,
    }


def _sample_avg_path(G: nx.Graph, sample_size: int) -> Optional[float]:
    """
    Approximate the average shortest path length via sampled Dijkstra.
    Operates on the largest connected component.
    """
    if G.number_of_nodes() < 2:
        return None

    # Use largest connected component
    if not nx.is_connected(G):
        lcc_nodes = max(nx.connected_components(G), key=len)
        G = G.subgraph(lcc_nodes)

    if G.number_of_nodes() < 2:
        return None

    import random
    nodes = list(G.nodes())
    sample = random.sample(nodes, min(sample_size, len(nodes)))

    lengths = []
    for src in sample:
        try:
            path_lengths = nx.single_source_dijkstra_path_length(G, src, weight="weight")
            lengths.extend(v for v in path_lengths.values() if v > 0)
        except Exception:
            continue

    return sum(lengths) / len(lengths) if lengths else None
