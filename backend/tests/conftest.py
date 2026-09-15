"""
Shared fixtures for the regression suite.

Two synthetic topologies are used deliberately:

  grid        - homogeneous 20x20 lattice. No chokepoints. Targeted attack does
                NOT dominate random failure here, which is the case that the
                removed clamp used to overwrite.
  chokepoint  - four dense districts joined by a single bridge chain. Road-like
                structure where targeted attack does dominate.

Testing against both is the point: a claim that only holds on one is not a
claim about road networks.
"""
import networkx as nx
import pytest

EDGE_ATTRS = dict(length=100.0, weight=100.0, speed_kph=30.0,
                  time_s=12.0, highway="residential")


def _decorate(G: nx.Graph) -> nx.Graph:
    for i, n in enumerate(sorted(G.nodes())):
        G.nodes[n].setdefault("x", 77.57 + (i % 40) * 0.001)
        G.nodes[n].setdefault("y", 12.92 + (i // 40) * 0.001)
    for u, v in G.edges():
        G.edges[u, v].update(EDGE_ATTRS)
    G.graph["artifact"] = "synthetic-fixture"
    G.graph["aoi_bbox"] = {"south": 12.92, "west": 77.57, "north": 12.99, "east": 77.64}
    return G


def make_grid(n: int = 20) -> nx.Graph:
    return _decorate(nx.convert_node_labels_to_integers(nx.grid_2d_graph(n, n)))


def make_chokepoint() -> nx.Graph:
    """Four 7x7 districts in a chain, joined by single edges."""
    H = nx.Graph()
    blocks = []
    for b in range(4):
        B = nx.convert_node_labels_to_integers(nx.grid_2d_graph(7, 7), first_label=b * 100)
        H.add_edges_from(B.edges())
        blocks.append(sorted(B.nodes()))
    H.add_edges_from([
        (blocks[0][-1], blocks[1][0]),
        (blocks[1][-1], blocks[2][0]),
        (blocks[2][-1], blocks[3][0]),
    ])
    H.graph["bridge_nodes"] = [blocks[0][-1], blocks[1][0], blocks[1][-1],
                               blocks[2][0], blocks[2][-1], blocks[3][0]]
    return _decorate(H)


@pytest.fixture
def grid():
    return make_grid()


@pytest.fixture
def chokepoint():
    return make_chokepoint()


@pytest.fixture
def path_graph():
    """A 6-node path: exactly one route exists, so no alternative can exist."""
    G = nx.path_graph(6)
    return _decorate(G)


@pytest.fixture(autouse=True)
def _isolate_graph_store():
    """Reset the global GraphStore between tests so state cannot leak."""
    from app.graph_pipeline.graph_build import GraphStore
    GraphStore._raw = None
    GraphStore._healed = None
    GraphStore._ml_healed = None
    GraphStore._last_simulation = None
    yield
    GraphStore._raw = None
    GraphStore._healed = None
    GraphStore._ml_healed = None
