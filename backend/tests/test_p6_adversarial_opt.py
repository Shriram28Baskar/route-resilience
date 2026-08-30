import pytest
import networkx as nx
from unittest.mock import patch
from app.simulation.routing import compute_relief_camps

def test_p6_euclidean_vs_network():
    # Construct a U-shaped graph where Euclidean distance is short, but network is long
    G = nx.Graph()
    # Path: 1 -- 2 -- 3 -- 4 -- 5
    # Nodes 1 and 5 are geometrically close, but topologically far.
    G.add_node(1, x=0, y=0)
    G.add_node(2, x=0, y=1)
    G.add_node(3, x=1, y=1)
    G.add_node(4, x=1, y=0)
    G.add_node(5, x=0.1, y=0) # geometrically near 1
    
    G.add_edge(1, 2, time_s=10)
    G.add_edge(2, 3, time_s=10)
    G.add_edge(3, 4, time_s=10)
    G.add_edge(4, 5, time_s=10)
    
    # We want to place k=2 camps.
    # We will mock the raster population so nodes 1 and 5 have huge demand.
    import sys
    from unittest.mock import patch
    
    with patch('app.simulation.routing._get_src') as mock_src:
        mock_src.return_value = None # Fallback to 0.0 weights naturally
        
        # Override weights inside the test by patching _get_distributed_node_weights
        with patch('app.simulation.routing._get_distributed_node_weights') as mock_weights:
            mock_weights.return_value = {1: 1000.0, 2: 1.0, 3: 1.0, 4: 1.0, 5: 1000.0}
            
            res = compute_relief_camps(G, k=2)
            camps = [int(c['id']) for c in res['camps']]
            
            # Since 1 and 5 have the highest demand, the camps MUST snap to 1 and 5 to minimize time_s.
            assert set(camps) == {1, 5}
            
            # Catchment assignment: node 2 is closer to 1 (time=10), node 4 is closer to 5 (time=10).
            # node 3 is time=20 from 1, and time=20 from 5.
            mapping = res['catchment_mapping']
            # We don't assert 3, but 2 goes to 1, 4 goes to 5.
            # Convert string keys back to int for checking
            mapping_int = {int(k): v for k,v in mapping.items()}
            
            c1_idx = [i for i, c in enumerate(res['camps']) if c['id'] == '1'][0]
            c5_idx = [i for i, c in enumerate(res['camps']) if c['id'] == '5'][0]
            
            assert mapping_int[2] == c1_idx
            assert mapping_int[4] == c5_idx

def test_p6_population_weighting_shift():
    # Graph: 1 -- 2 -- 3 -- 4 -- 5
    G = nx.Graph()
    for i in range(1, 6):
        G.add_node(i, x=i, y=0)
    for i in range(1, 5):
        G.add_edge(i, i+1, time_s=10)
        
    with patch('app.simulation.routing._get_distributed_node_weights') as mock_weights:
        # Heavily weight node 5
        mock_weights.return_value = {1: 1.0, 2: 1.0, 3: 1.0, 4: 1.0, 5: 10000.0}
        
        # With k=1, the camp must shift all the way to 5
        res = compute_relief_camps(G, k=1)
        assert res['camps'][0]['id'] == '5'
        
        # Ensure total population matches exactly 10004
        assert res['metrics']['total_population_served'] == 10004

def test_p6_metrics_and_unreachable():
    G = nx.Graph()
    G.add_node(1, x=0, y=0)
    G.add_node(2, x=1, y=0)
    G.add_edge(1, 2, time_s=5)
    
    # Node 3 is isolated (flooded out)
    G.add_node(3, x=2, y=0)
    
    with patch('app.simulation.routing._get_distributed_node_weights') as mock_weights:
        # Only LCC (1, 2) gets passed to weight generation
        mock_weights.return_value = {1: 50.0, 2: 50.0}
        
        res = compute_relief_camps(G, k=1)
        metrics = res['metrics']
        
        assert metrics['unreachable_nodes_count'] == 1
        # Network coverage is 2/3 = 66.7%
        assert metrics['network_coverage_pct'] == 66.7
        # Population served is exactly 100
        assert metrics['total_population_served'] == 100

def test_p6_k_larger_than_nodes():
    G = nx.Graph()
    G.add_node(1, x=0, y=0)
    G.add_node(2, x=1, y=1)
    G.add_edge(1, 2, time_s=1)
    
    res = compute_relief_camps(G, k=5)
    assert len(res['camps']) == 2
    assert res['metrics']['network_coverage_pct'] == 100.0

