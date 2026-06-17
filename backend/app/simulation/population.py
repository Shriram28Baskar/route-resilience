"""
Population Impact Analysis.
Estimates the number of people isolated by a disaster by mapping
population data to road network nodes and computing accessibility.
"""
import logging
from typing import Dict, Any

import networkx as nx

logger = logging.getLogger(__name__)

# Base population of Bengaluru (approx)
TOTAL_POPULATION = 13_600_000 

def estimate_population_impact(
    baseline_G: nx.Graph,
    perturbed_G: nx.Graph,
    total_population: int = TOTAL_POPULATION
) -> Dict[str, Any]:
    """
    Estimates the number of people affected/isolated by a disaster.
    
    This uses a simplified heuristic: population is distributed 
    proportionally to nodes in the largest connected component (LCC).
    When nodes are ablated or disconnected from the LCC, the corresponding
    population is considered 'isolated'.
    
    Args:
        baseline_G: The original, healthy graph.
        perturbed_G: The graph after disaster node ablation.
        total_population: Estimated total population for the AOI.
        
    Returns:
        Dict with keys:
        - total_affected (int): Population on nodes directly ablated or disconnected.
        - isolated_count (int): Number of nodes isolated.
        - percent_affected (float): Percentage of total population affected.
    """
    if baseline_G.number_of_nodes() == 0:
        return {
            "total_affected": 0,
            "isolated_count": 0,
            "percent_affected": 0.0
        }

    # Identify LCC in baseline
    if nx.is_connected(baseline_G):
        baseline_lcc_nodes = set(baseline_G.nodes())
    else:
        baseline_lcc_nodes = max(nx.connected_components(baseline_G), key=len)

    baseline_lcc_size = len(baseline_lcc_nodes)
    if baseline_lcc_size == 0:
        baseline_lcc_size = 1 # Avoid div by zero

    # Distribute population evenly across LCC nodes
    # (In a real system, we would map census/WorldPop rasters to nodes)
    pop_per_node = total_population / baseline_lcc_size

    # Identify LCC in perturbed graph
    if nx.is_connected(perturbed_G):
        perturbed_lcc_nodes = set(perturbed_G.nodes())
    elif perturbed_G.number_of_nodes() > 0:
        perturbed_lcc_nodes = max(nx.connected_components(perturbed_G), key=len)
    else:
        perturbed_lcc_nodes = set()

    # Isolated nodes are those that were in the baseline LCC but are no longer
    # in the perturbed LCC (either because they were ablated or disconnected).
    isolated_nodes = set(baseline_lcc_nodes) - set(perturbed_lcc_nodes)
    isolated_count = len(isolated_nodes)
    
    total_affected = int(isolated_count * pop_per_node)
    percent_affected = round((total_affected / total_population) * 100, 2)
    
    logger.info(f"Population impact: {isolated_count} isolated nodes, {total_affected} people ({percent_affected}%)")

    return {
        "total_affected": total_affected,
        "isolated_count": isolated_count,
        "percent_affected": percent_affected
    }
