import pytest
import networkx as nx
from app.simulation.population import estimate_population_impact
from app.simulation.timeline import run_progression_timeline

def test_estimate_population_impact():
    # Baseline graph: 4 nodes, fully connected
    G = nx.Graph()
    G.add_edges_from([(1, 2), (2, 3), (3, 4), (4, 1)])
    
    # Perturbed graph: node 4 is ablated
    G_pert = nx.Graph()
    G_pert.add_edges_from([(1, 2), (2, 3)])
    
    # With 4 nodes in baseline LCC, pop_per_node = 100 / 4 = 25
    # Perturbed LCC has 3 nodes (1, 2, 3). Node 4 is isolated.
    # Total isolated nodes = 1.
    res = estimate_population_impact(G, G_pert, total_population=100)
    
    assert res["isolated_count"] == 1
    assert res["total_affected"] == 25
    assert res["percent_affected"] == 25.0

def test_run_progression_timeline():
    # Graph with 5 nodes
    G = nx.Graph()
    G.add_edges_from([(1, 2), (2, 3), (3, 4), (4, 5)])
    for n in G.nodes():
        G.nodes[n]['x'] = 0
        G.nodes[n]['y'] = 0
        
    for u, v in G.edges():
        G.edges[u, v]['weight'] = 1.0
        
    # Initial strike on node 3
    seeds = [3]
    timeline = run_progression_timeline(G, seeds, repair_rate=1, max_days=10)
    
    # Day 0: Baseline
    assert timeline[0]["day"] == 0
    assert timeline[0]["active_ablated_count"] == 0
    
    # Day 1: Initial Strike
    assert timeline[1]["day"] == 1
    assert timeline[1]["active_ablated_count"] == 1
    assert 3 in timeline[1]["affected_nodes"]
    
    # Check that there is a Recovery phase
    recovery_days = [d for d in timeline if "Recover" in d["phase"]]
    assert len(recovery_days) > 0
    
    # Eventually it should be fully recovered
    assert timeline[-1]["active_ablated_count"] == 0
