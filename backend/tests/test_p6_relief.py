import pytest
import networkx as nx
from app.simulation.routing import compute_relief_camps
from unittest.mock import patch

def test_relief_camps_normal():
    # Build a simple grid graph
    G = nx.grid_2d_graph(4, 4)
    for u, v in G.edges():
        G[u][v]['weight'] = 1.0
    for n in G.nodes():
        G.nodes[n]['x'] = n[1]
        G.nodes[n]['y'] = n[0]
        
    with patch('app.simulation.routing._get_distributed_node_weights') as mock_weights:
        mock_weights.return_value = {n: 100.0 for n in G.nodes()}
        
        result = compute_relief_camps(G, k=2)
        
        camps = result.get("camps", [])
        assert len(camps) == 2
        
        # Test population sum
        total_pop = sum(c["population_estimate"] for c in camps)
        assert total_pop == 1600  # 16 nodes * 100
        
        # Check catchment mapping assigns every node
        mapping = result.get("catchment_mapping", {})
        assert len(mapping) == 16

def test_relief_camps_empty():
    G = nx.Graph()
    result = compute_relief_camps(G, k=3)
    assert result["camps"] == []
    assert result["catchment_mapping"] == {}

def test_relief_camps_k_larger_than_nodes():
    G = nx.Graph()
    G.add_node(1, x=0, y=0)
    G.add_node(2, x=1, y=1)
    G.add_edge(1, 2)
    
    with patch('app.simulation.routing._get_distributed_node_weights') as mock_weights:
        mock_weights.return_value = {1: 100.0, 2: 100.0}
        
        result = compute_relief_camps(G, k=5)
        camps = result.get("camps", [])
        assert len(camps) == 2
        assert len(result.get("catchment_mapping")) == 2

