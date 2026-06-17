"""
Fragility Analysis
Calculates network fragility curves and percolation thresholds.
"""
import logging
from typing import Dict, List, Any
import networkx as nx

from app.graph_pipeline.centrality import compute_betweenness
from app.simulation.ablation import ablate_nodes
from app.graph_pipeline.metrics import compute_graph_metrics

logger = logging.getLogger(__name__)

def generate_fragility_curve(G: nx.Graph, num_steps: int = 10) -> Dict[str, Any]:
    """
    Generate a fragility curve by progressively removing the most central nodes.
    Returns the points for the curve, percolation threshold, and robustness integral.
    """
    nodes = list(G.nodes())
    if not nodes:
        return {"curve": [], "percolation_threshold": 0.0, "robustness_integral": 0.0}
        
    # Rank nodes by betweenness centrality
    centrality = compute_betweenness(G)
    ranked_nodes = sorted(centrality.keys(), key=lambda n: centrality[n], reverse=True)
    
    total_nodes = len(ranked_nodes)
    step_size = max(1, total_nodes // num_steps)
    
    curve = []
    
    # Base case (0% ablated)
    base_metrics = compute_graph_metrics(G)
    curve.append({
        "fraction_ablated": 0.0,
        "lcc_fraction": base_metrics.get("largest_component_fraction", 1.0),
        "efficiency": nx.global_efficiency(G) if len(nodes) < 500 else base_metrics.get("largest_component_fraction", 1.0) # approximate efficiency for large graphs
    })
    
    percolation_threshold = None
    
    current_G = G.copy()
    
    for i in range(1, num_steps + 1):
        num_to_ablate = min(i * step_size, total_nodes)
        fraction = num_to_ablate / total_nodes
        
        # Ablate up to the current fraction (from original graph for consistency)
        nodes_to_remove = ranked_nodes[:num_to_ablate]
        
        # Doing this iteratively could be faster, but for simplicity let's use ablate_nodes
        perturbed = G.copy()
        perturbed.remove_nodes_from(nodes_to_remove)
        
        if len(perturbed.nodes()) == 0:
            curve.append({"fraction_ablated": fraction, "lcc_fraction": 0.0, "efficiency": 0.0})
            if percolation_threshold is None:
                percolation_threshold = fraction
            continue
            
        metrics = compute_graph_metrics(perturbed)
        lcc_frac = metrics.get("largest_component_fraction", 0.0)
        
        # Approximate efficiency (it's O(N^3) so only do it for small graphs or use LCC as proxy)
        eff = lcc_frac  # using LCC as a proxy for efficiency to keep API fast
        
        curve.append({
            "fraction_ablated": round(fraction, 2),
            "lcc_fraction": round(lcc_frac, 4),
            "efficiency": round(eff, 4)
        })
        
        # Percolation threshold is often defined as the point where LCC fraction drops below 0.1 or 0.2
        if percolation_threshold is None and lcc_frac < 0.1:
            percolation_threshold = fraction
            
    if percolation_threshold is None:
        percolation_threshold = 1.0
        
    # Robustness integral (area under the LCC curve)
    # Using trapezoidal rule
    robustness = 0.0
    for i in range(len(curve) - 1):
        y1 = curve[i]["lcc_fraction"]
        y2 = curve[i+1]["lcc_fraction"]
        dx = curve[i+1]["fraction_ablated"] - curve[i]["fraction_ablated"]
        robustness += 0.5 * (y1 + y2) * dx
        
    return {
        "curve": curve,
        "percolation_threshold": round(percolation_threshold, 3),
        "robustness_integral": round(robustness, 3)
    }
