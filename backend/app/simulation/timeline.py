"""
Disaster Progression Timeline Simulation.
Models a step-by-step progression of a disaster scenario:
Day 0: Baseline
Day 1: Initial strike (ablating seed nodes)
Days 2-4: Cascading failures based on centrality threshold
Days 5+: Recovery based on repair rate
"""
import logging
from typing import List, Dict, Any

import networkx as nx

from app.graph_pipeline.metrics import compute_graph_metrics
from app.graph_pipeline.centrality import compute_betweenness
from app.simulation.ablation import ablate_nodes
from app.simulation.population import estimate_population_impact

logger = logging.getLogger(__name__)

def run_progression_timeline(
    G_baseline: nx.Graph,
    seed_node_ids: List[Any],
    repair_rate: int = 2,
    max_days: int = 10
) -> List[Dict[str, Any]]:
    """
    Run a full disaster progression timeline.
    
    Args:
        G_baseline: The healthy baseline graph.
        seed_node_ids: Nodes affected on Day 1.
        repair_rate: Number of nodes repaired per day during recovery phase.
        max_days: Maximum number of simulation days.
        
    Returns:
        List of daily state dictionaries.
    """
    timeline = []
    
    # Track the current state
    current_G = G_baseline.copy()
    ablated_nodes = set()
    
    # Pre-compute baseline metrics
    baseline_metrics = compute_graph_metrics(G_baseline)
    baseline_lcc_size = baseline_metrics.get("largest_component_size", 1)
    if baseline_lcc_size == 0: baseline_lcc_size = 1
    
    def _record_day(day: int, phase: str, ablated_count: int, G_current: nx.Graph, new_nodes: List[Any] = None) -> None:
        metrics = compute_graph_metrics(G_current)
        pop_impact = estimate_population_impact(G_baseline, G_current)
        
        # Calculate Global Resilience Score (GRS)
        lcc_fraction = metrics.get("largest_component_fraction", 0.0)
        density = metrics.get("density", 0.0)
        # Scale density so it contributes nicely (density usually very small for road networks, e.g., 0.0001)
        # Let's normalize against baseline density
        baseline_density = baseline_metrics.get("density", 1.0)
        if baseline_density == 0: baseline_density = 1.0
        density_ratio = min(1.0, density / baseline_density)
        
        # Simple heuristic for GRS: weighted combination of connectivity and population isolation
        isolated_frac = pop_impact["percent_affected"] / 100.0
        grs = (0.7 * lcc_fraction) + (0.3 * (1.0 - isolated_frac))
        
        timeline.append({
            "day": day,
            "phase": phase,
            "active_ablated_count": ablated_count,
            "global_resilience_score": round(grs, 4),
            "isolated_population": pop_impact["total_affected"],
            "lcc_fraction": round(lcc_fraction, 4),
            "affected_nodes": new_nodes or [],
            "metrics": metrics
        })

    # Day 0: Baseline
    _record_day(0, "Baseline", 0, G_baseline)

    # Filter invalid seeds
    valid_seeds = [n for n in seed_node_ids if n in G_baseline]
    if not valid_seeds:
        return timeline
        
    # Day 1: Initial Strike
    ablated_nodes.update(valid_seeds)
    current_G = ablate_nodes(G_baseline, list(ablated_nodes))
    _record_day(1, "Initial Strike", len(ablated_nodes), current_G, new_nodes=valid_seeds)

    # Days 2-4: Cascading Failures
    cascade_days = min(3, max_days - 1)
    for day in range(2, 2 + cascade_days):
        if len(current_G.nodes()) < 2:
            break
            
        centrality = compute_betweenness(current_G, k=10)
        max_cent = max(centrality.values()) if centrality else 0
        threshold = 0.7 * max_cent if max_cent > 0 else float('inf')
        
        newly_stressed = [n for n, c in centrality.items() if c >= threshold]
        
        if newly_stressed:
            ablated_nodes.update(newly_stressed)
            current_G = ablate_nodes(G_baseline, list(ablated_nodes))
            _record_day(day, "Cascading Failure", len(ablated_nodes), current_G, new_nodes=newly_stressed)
        else:
            _record_day(day, "Stabilized", len(ablated_nodes), current_G, new_nodes=[])
            
    # Days 5+: Recovery Phase
    current_day = 2 + cascade_days
    while ablated_nodes and current_day <= max_days:
        # Prioritize repairing nodes with highest historical centrality
        # In a real system, we might compute centrality on baseline to prioritize
        baseline_cent = compute_betweenness(G_baseline)
        ablated_list = list(ablated_nodes)
        ablated_list.sort(key=lambda n: baseline_cent.get(n, 0), reverse=True)
        
        repaired = ablated_list[:repair_rate]
        for r in repaired:
            ablated_nodes.remove(r)
            
        current_G = ablate_nodes(G_baseline, list(ablated_nodes))
        phase = "Recovery" if ablated_nodes else "Fully Recovered"
        _record_day(current_day, phase, len(ablated_nodes), current_G, new_nodes=repaired)
        current_day += 1

    return timeline
