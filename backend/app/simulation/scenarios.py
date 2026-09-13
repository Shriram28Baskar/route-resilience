"""
Multi-Scenario Simulation
Evaluates multiple disaster scenarios and compares their impacts.
"""
import logging
from typing import List, Dict, Any

import networkx as nx
from app.simulation.ablation import ablate_nodes
from app.simulation.resilience import compute_resilience_index
from app.graph_pipeline.metrics import compute_graph_metrics

logger = logging.getLogger(__name__)

def run_multi_scenario(G: nx.Graph, scenarios: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    Run multiple ablation scenarios and return a list of comparative metrics.
    """
    results = []
    
    # Map string IDs back to graph node keys
    node_map = {str(n): n for n in G.nodes()}
    
    for s in scenarios:
        target_nodes = [node_map[nid] for nid in s["ablated_node_ids"] if nid in node_map]
        
        if not target_nodes:
            # Baseline or invalid scenario — use fast=True to skip expensive Dijkstra path lengths
            metrics = compute_graph_metrics(G, fast=True)
            results.append({
                "name": s["name"],
                "description": s["description"],
                "ablated_count": 0,
                "ri": 1.0,
                "lcc_fraction": metrics.get("largest_component_fraction", 1.0),
                "avg_path_length": metrics.get("avg_shortest_path_length", 0.0),
                "efficiency": metrics.get("largest_component_fraction", 1.0)
            })
            continue
            
        perturbed = ablate_nodes(G, target_nodes)
        # fast=True skips the expensive 50-Dijkstra avg_path_length (only used as proxy anyway)
        metrics = compute_graph_metrics(perturbed, fast=True)
        # Reduced sample_size: 25 is sufficient for a 13k-node graph (was 60)
        ri_data = compute_resilience_index(G, perturbed, sample_size=25)
        
        results.append({
            "name": s["name"],
            "description": s["description"],
            "ablated_count": len(target_nodes),
            "ri": round(ri_data["resilience_index"] or 0, 4),
            "lcc_fraction": round(metrics.get("largest_component_fraction", 0.0), 4),
            "avg_path_length": round(metrics.get("average_shortest_path_length", 0.0) or 0.0, 4),
            "efficiency": round(metrics.get("largest_component_fraction", 0.0), 4)
        })
        
    return results
