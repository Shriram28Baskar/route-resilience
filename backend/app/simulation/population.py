"""
Population impact for ablation (node-removal) scenarios.

IMPORTANT METHODOLOGICAL NOTE
------------------------------
Estimating population impact from node ablation requires spatially assigning
population to road nodes — e.g., by computing Voronoi regions around nodes
and summing WorldPop raster population within each region.

This spatial join is NOT implemented in the current system.

The previous version of this module divided 13.6M people evenly across all
road nodes (pop_per_node = total_population / node_count). This assumption
is methodologically unsound — road nodes are not evenly distributed by
population, and mixing industrial, residential, and highway nodes equally
produces meaningless numbers.

That fake calculation has been removed (audit fix C3, 2026-08-28).

For flood scenarios, population IS correctly estimated via WorldPop raster
bbox query in backend/app/data/population.py — use that instead.

What this module now returns
-----------------------------
A structured data-gap response that:
- Reports the number of network nodes removed/isolated (which IS real and computed)
- Clearly states that population estimation is not available for this scenario type
- Directs users to the flood impact endpoint (/accessibility/flood-impact) for
  population figures backed by WorldPop spatial raster data

This is a deliberate choice to report less rather than fabricate.
"""
import logging
from typing import Dict, Any

import networkx as nx

logger = logging.getLogger(__name__)


def estimate_population_impact(
    baseline_G: nx.Graph,
    perturbed_G: nx.Graph,
) -> Dict[str, Any]:
    """
    Report network isolation metrics from node ablation.

    DOES NOT estimate population — spatial population assignment
    to road nodes is not implemented. See module docstring.

    Returns:
        Dict with:
        - isolated_nodes (int): nodes removed from LCC by ablation
        - lcc_fraction_retained (float): fraction of LCC retained post-ablation
        - population_note (str): explicit data-gap explanation
    """
    if baseline_G.number_of_nodes() == 0:
        return {
            "isolated_nodes": 0,
            "lcc_fraction_retained": 1.0,
            "population_note": "Graph is empty.",
        }

    # Baseline LCC
    if nx.is_connected(baseline_G):
        baseline_lcc = set(baseline_G.nodes())
    else:
        baseline_lcc = set(max(nx.connected_components(baseline_G), key=len))

    # Perturbed LCC
    if perturbed_G.number_of_nodes() == 0:
        perturbed_lcc = set()
    elif nx.is_connected(perturbed_G):
        perturbed_lcc = set(perturbed_G.nodes())
    else:
        perturbed_lcc = set(max(nx.connected_components(perturbed_G), key=len))

    isolated_nodes = len(baseline_lcc - perturbed_lcc)
    lcc_fraction = len(perturbed_lcc) / len(baseline_lcc) if baseline_lcc else 1.0

    logger.info(
        f"Ablation network impact: {isolated_nodes} nodes isolated from LCC. "
        f"LCC retained: {lcc_fraction:.2%}. Population not estimated."
    )

    return {
        "isolated_nodes": isolated_nodes,
        "lcc_fraction_retained": round(lcc_fraction, 4),
        "population_note": (
            "Population impact not estimated for node-ablation scenarios. "
            "Spatially assigning WorldPop raster population to individual road nodes "
            "requires Voronoi region computation, which is not implemented. "
            "For population figures, use /accessibility/flood-impact with a "
            "flood-scenario node list — that endpoint uses actual WorldPop spatial data."
        ),
    }
