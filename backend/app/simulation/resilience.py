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

# Speed lookup by road type (m/s) — OSM highway tag values
# Source: IRC (Indian Roads Congress) recommended speeds
ROAD_SPEED_MPS: dict = {
    "motorway":      33.33,   # 120 km/h
    "trunk":         27.78,   # 100 km/h
    "primary":       22.22,   # 80 km/h
    "secondary":     16.67,   # 60 km/h
    "tertiary":      13.89,   # 50 km/h
    "residential":    8.33,   # 30 km/h
    "service":        5.56,   # 20 km/h
    "footway":        1.39,   # 5 km/h (walking)
    "cycleway":       4.17,   # 15 km/h
    "unclassified":  11.11,   # 40 km/h
    "default":        8.33,   # 30 km/h fallback
}


def get_road_speed(highway_type: str) -> float:
    """Return speed in m/s for a given OSM highway type."""
    return ROAD_SPEED_MPS.get(highway_type, ROAD_SPEED_MPS["default"])


import weakref

_baseline_cache = weakref.WeakKeyDictionary()

def compute_resilience_index(
    baseline_G: nx.Graph,
    perturbed_G: nx.Graph,
    sample_size: int = 60,
) -> Dict[str, Any]:
    """
    Compute Resilience Index using deterministic sampling and disconnection penalties.
    """
    import random
    
    # 1. Deterministic sample of nodes from the baseline graph
    nodes = sorted(list(baseline_G.nodes()))
    rng = random.Random(999) # Use different seed from simulation's Random Failure!
    sources = rng.sample(nodes, min(sample_size, len(nodes)))

    # 2. Compute baseline or get from cache
    if baseline_G in _baseline_cache and _baseline_cache[baseline_G].get(sample_size):
        baseline_avg, baseline_counts = _baseline_cache[baseline_G][sample_size]
    else:
        baseline_avg, baseline_counts = _compute_baseline_paths(baseline_G, sources)
        if baseline_G not in _baseline_cache:
            _baseline_cache[baseline_G] = {}
        _baseline_cache[baseline_G][sample_size] = (baseline_avg, baseline_counts)

    # 3. Compute perturbed with penalties
    perturbed_avg = _compute_perturbed_paths(perturbed_G, sources, baseline_counts)

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


def _compute_baseline_paths(G: nx.Graph, sources: list):
    lengths = []
    reachable_counts = {}
    for src in sources:
        if src not in G:
            continue
        try:
            path_lengths = nx.single_source_dijkstra_path_length(G, src, weight="time_s")
            reachable = [v for v in path_lengths.values() if v > 0]
            lengths.extend(reachable)
            reachable_counts[src] = len(reachable)
        except Exception:
            reachable_counts[src] = 0
            
    avg = sum(lengths) / len(lengths) if lengths else None
    return avg, reachable_counts

def _compute_perturbed_paths(G: nx.Graph, sources: list, baseline_counts: dict):
    lengths = []
    # Use 3600 seconds (1 hour) as the penalty for a broken/unreachable path
    PENALTY = 3600.0 
    
    for src in sources:
        expected = baseline_counts.get(src, 0)
        if src not in G:
            # Source ablated! All its previous paths are broken.
            lengths.extend([PENALTY] * expected)
            continue
            
        try:
            path_lengths = nx.single_source_dijkstra_path_length(G, src, weight="time_s")
            reachable = [v for v in path_lengths.values() if v > 0]
            lengths.extend(reachable)
            
            # Penalize missing destinations
            missing = expected - len(reachable)
            if missing > 0:
                lengths.extend([PENALTY] * missing)
        except Exception:
            lengths.extend([PENALTY] * expected)

    return sum(lengths) / len(lengths) if lengths else None
