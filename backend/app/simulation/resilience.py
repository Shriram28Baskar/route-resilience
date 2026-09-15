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

# Default penalty (seconds) charged for an origin-destination pair that was
# reachable in the baseline and is unreachable after perturbation.
#
# This value is ARBITRARY. It is not derived from data. It exists because the
# alternative (dropping unreachable pairs) makes a severed network appear to
# IMPROVE. Every RI produced by this module is conditional on it, so it is an
# explicit parameter, it is echoed in the result, and its effect on intervention
# rankings must be checked with a sensitivity sweep before any RI is published.
DEFAULT_PENALTY_S: float = 3600.0


def compute_resilience_index(
    baseline_G: nx.Graph,
    perturbed_G: nx.Graph,
    sample_size: int = 60,
    penalty_s: float = DEFAULT_PENALTY_S,
) -> Dict[str, Any]:
    """
    Compute the Resilience Index and its penalty-free decomposition.

    RI = baseline_mean_path_time / perturbed_mean_path_time, where pairs that
    became unreachable are charged `penalty_s`.

    RI is BOUNDED BELOW by baseline_mean / penalty_s. That floor is a function of
    the network's own baseline path times, so **RI is not comparable across
    networks**. For any cross-network claim use the two penalty-free quantities
    returned alongside it:

      * ``unreachable_fraction``  - share of baseline-reachable pairs severed.
      * ``reachable_path_inflation`` - mean path-time ratio computed ONLY over
        pairs reachable in both graphs. Independent of `penalty_s`.

    Together these fully characterise the damage without an arbitrary constant.
    No single normalised scalar is offered: collapsing "longer" and "impossible"
    into one number requires a weighting between them that this module has no
    principled basis to choose.
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

    # 3. Compute perturbed with penalties, plus the penalty-free decomposition
    perturbed_avg, decomp = _compute_perturbed_paths(
        perturbed_G, sources, baseline_counts, penalty_s, baseline_G
    )

    is_disconnected = (perturbed_G.number_of_nodes() > 0
                       and not nx.is_connected(perturbed_G))
    partition_count = nx.number_connected_components(perturbed_G)

    if baseline_avg is not None and perturbed_avg is not None and perturbed_avg > 0:
        ri = baseline_avg / perturbed_avg
    else:
        ri = None

    ri_floor = (baseline_avg / penalty_s) if (baseline_avg is not None and penalty_s > 0) else None

    logger.info(f"Resilience Index: R={ri}, baseline={baseline_avg}, perturbed={perturbed_avg}, "
                f"penalty_s={penalty_s}, disconnected={is_disconnected}")

    return {
        "resilience_index": round(ri, 4) if ri is not None else None,
        "baseline_avg_path": round(baseline_avg, 4) if baseline_avg is not None else None,
        "perturbed_avg_path": round(perturbed_avg, 4) if perturbed_avg is not None else None,
        "disconnected": is_disconnected,
        "partition_count": partition_count,
        # --- provenance of the metric -------------------------------------
        "penalty_s": penalty_s,
        "sample_size": sample_size,
        "ri_floor": round(ri_floor, 6) if ri_floor is not None else None,
        "ri_is_cross_network_comparable": False,
        # --- penalty-free decomposition ------------------------------------
        "unreachable_fraction": decomp["unreachable_fraction"],
        "reachable_path_inflation": decomp["reachable_path_inflation"],
        "pairs_evaluated": decomp["pairs_evaluated"],
        "pairs_severed": decomp["pairs_severed"],
    }


def _compute_baseline_paths(G: nx.Graph, sources: list):
    """Return (mean_baseline_path_time, {src: {tgt: time}}) over the sampled sources."""
    lengths = []
    reachable_map = {}
    for src in sources:
        if src not in G:
            reachable_map[src] = {}
            continue
        try:
            path_lengths = nx.single_source_dijkstra_path_length(G, src, weight="time_s")
            reachable = {t: d for t, d in path_lengths.items() if d > 0}
            lengths.extend(reachable.values())
            reachable_map[src] = reachable
        except Exception:
            reachable_map[src] = {}

    avg = sum(lengths) / len(lengths) if lengths else None
    return avg, reachable_map


def _compute_perturbed_paths(G: nx.Graph, sources: list, baseline_map: dict,
                             penalty_s: float, baseline_G: nx.Graph = None):
    """
    Mean perturbed path time with `penalty_s` charged for severed pairs, plus a
    penalty-free decomposition computed over the same sampled pairs.

    Returns (mean_perturbed_path_time, decomposition_dict).
    """
    lengths = []
    pairs_total = 0          # baseline-reachable pairs considered
    pairs_severed = 0        # of those, now unreachable
    both_base, both_pert = [], []   # matched pairs reachable in BOTH graphs

    for src in sources:
        expected = baseline_map.get(src, {})
        pairs_total += len(expected)

        if src not in G:
            # Source itself ablated: every pair it had is severed.
            lengths.extend([penalty_s] * len(expected))
            pairs_severed += len(expected)
            continue

        try:
            path_lengths = nx.single_source_dijkstra_path_length(G, src, weight="time_s")
            reachable = {t: d for t, d in path_lengths.items() if d > 0}
        except Exception:
            lengths.extend([penalty_s] * len(expected))
            pairs_severed += len(expected)
            continue

        for tgt, base_d in expected.items():
            if tgt in reachable:
                lengths.append(reachable[tgt])
                both_base.append(base_d)
                both_pert.append(reachable[tgt])
            else:
                lengths.append(penalty_s)
                pairs_severed += 1

    mean_perturbed = sum(lengths) / len(lengths) if lengths else None

    inflation = None
    if both_base and sum(both_base) > 0:
        inflation = round((sum(both_pert) / len(both_pert)) /
                          (sum(both_base) / len(both_base)), 6)

    decomposition = {
        "unreachable_fraction": (round(pairs_severed / pairs_total, 6)
                                 if pairs_total else None),
        "reachable_path_inflation": inflation,
        "pairs_evaluated": pairs_total,
        "pairs_severed": pairs_severed,
    }
    return mean_perturbed, decomposition
