"""
MST-based topological healing for fragmented road graphs.

Algorithm:
1. Identify disconnected components via Union-Find.
2. Enumerate candidate bridge edges between each pair of components
   (limited to top-K nearest inter-component node pairs).
3. Score candidates by Euclidean distance + angular alignment penalty.
4. Build a "component graph" weighted by candidate edge scores.
5. Find the MST of the component graph → minimal set of bridges needed to
   connect all components.
6. Add those bridge edges to the original graph.
"""
import logging
import math
from itertools import combinations
from typing import List, Tuple, Dict, Set

import numpy as np
import networkx as nx

logger = logging.getLogger(__name__)

MAX_BRIDGE_DISTANCE = 0.005     # degrees (~500 m) — max gap to bridge
ANGLE_PENALTY_WEIGHT = 0.3      # how much to penalize angular misalignment
TOP_K_CANDIDATES = 5            # top-K nearest pairs per component pair


def heal_graph(G: nx.Graph) -> nx.Graph:
    """
    Return a topologically healed copy of G where disconnected components
    are bridged using MST-based gap closing.
    """
    healed = G.copy()
    components = list(nx.connected_components(healed))

    if len(components) <= 1:
        logger.info("Graph already connected — no healing needed.")
        return healed

    logger.info(f"Healing graph: {len(components)} components → merging …")

    # Build component centroid map and representative nodes
    comp_nodes: Dict[int, List] = {i: list(c) for i, c in enumerate(components)}

    # Find candidate bridge edges between all component pairs
    candidates = _find_candidates(healed, comp_nodes)

    if not candidates:
        logger.warning("No valid bridge candidates found within distance threshold.")
        return healed

    # Build component-level MST to find the minimal set of bridges
    comp_graph = nx.Graph()
    for comp_i, comp_j, u, v, score in candidates:
        if not comp_graph.has_edge(comp_i, comp_j) or comp_graph[comp_i][comp_j]["score"] > score:
            comp_graph.add_edge(comp_i, comp_j, score=score, bridge_u=u, bridge_v=v)

    mst = nx.minimum_spanning_tree(comp_graph, weight="score")

    # Add bridge edges to the healed graph
    bridges_added = 0
    for comp_i, comp_j, data in mst.edges(data=True):
        u, v = data["bridge_u"], data["bridge_v"]
        u_data = healed.nodes[u]
        v_data = healed.nodes[v]
        dist = _euclidean(u_data, v_data)
        healed.add_edge(u, v, length=dist, weight=dist, is_bridge=True)
        bridges_added += 1

    logger.info(f"Healing complete: added {bridges_added} bridge edges, "
                f"components reduced from {len(components)} → {nx.number_connected_components(healed)}")
    return healed


def _find_candidates(
    G: nx.Graph,
    comp_nodes: Dict[int, List],
) -> List[Tuple[int, int, int, int, float]]:
    """
    For each pair of components, find the TOP_K_CANDIDATES nearest cross-component
    node pairs and score them (lower = better).

    Returns list of (comp_i, comp_j, node_u, node_v, score).
    """
    candidates = []
    comp_ids = list(comp_nodes.keys())

    for comp_i, comp_j in combinations(comp_ids, 2):
        nodes_i = comp_nodes[comp_i]
        nodes_j = comp_nodes[comp_j]

        # Sample if components are large (avoid O(n²) for big graphs)
        sample_i = nodes_i[:200] if len(nodes_i) > 200 else nodes_i
        sample_j = nodes_j[:200] if len(nodes_j) > 200 else nodes_j

        pairs = []
        for u in sample_i:
            for v in sample_j:
                dist = _euclidean(G.nodes[u], G.nodes[v])
                if dist <= MAX_BRIDGE_DISTANCE:
                    angle_score = _angle_alignment_penalty(G, u, v)
                    score = dist * (1 + ANGLE_PENALTY_WEIGHT * angle_score)
                    pairs.append((u, v, score))

        # Keep top-K by score
        pairs.sort(key=lambda x: x[2])
        for u, v, score in pairs[:TOP_K_CANDIDATES]:
            candidates.append((comp_i, comp_j, u, v, score))

    return candidates


def _euclidean(node_a: dict, node_b: dict) -> float:
    """Euclidean distance in degree-space between two node attribute dicts."""
    dx = node_a.get("x", 0) - node_b.get("x", 0)
    dy = node_a.get("y", 0) - node_b.get("y", 0)
    return math.hypot(dx, dy)


def _angle_alignment_penalty(G: nx.Graph, u: int, v: int) -> float:
    """
    Compute an angular alignment penalty [0, 1] for a bridge edge (u, v).

    Idea: the bridge should continue in the same direction as the existing
    road segments at u and v. A sharp angle change → high penalty.

    Returns 0 (no penalty) if the bridge is well-aligned, 1 if perpendicular.
    """
    u_dir = _dominant_direction(G, u)
    v_dir = _dominant_direction(G, v)

    bridge_vec = np.array([G.nodes[v].get("x", 0) - G.nodes[u].get("x", 0),
                            G.nodes[v].get("y", 0) - G.nodes[u].get("y", 0)])
    bridge_norm = np.linalg.norm(bridge_vec)
    if bridge_norm < 1e-9:
        return 1.0
    bridge_unit = bridge_vec / bridge_norm

    penalties = []
    for direction in [u_dir, v_dir]:
        if direction is None:
            continue
        cos_sim = abs(np.dot(direction, bridge_unit))
        penalties.append(1.0 - cos_sim)   # 0 = aligned, 1 = perpendicular

    return float(np.mean(penalties)) if penalties else 0.5


def _dominant_direction(G: nx.Graph, node: int):
    """
    Return the unit vector of the dominant road direction at `node`
    (average direction of incident edges), or None if node is isolated.
    """
    neighbors = list(G.neighbors(node))
    if not neighbors:
        return None

    u_data = G.nodes[node]
    vecs = []
    for nb in neighbors:
        nb_data = G.nodes[nb]
        vec = np.array([nb_data.get("x", 0) - u_data.get("x", 0),
                        nb_data.get("y", 0) - u_data.get("y", 0)])
        norm = np.linalg.norm(vec)
        if norm > 1e-9:
            vecs.append(vec / norm)

    if not vecs:
        return None

    mean_vec = np.mean(vecs, axis=0)
    norm = np.linalg.norm(mean_vec)
    return mean_vec / norm if norm > 1e-9 else None
