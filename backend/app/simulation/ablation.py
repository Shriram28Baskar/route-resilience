"""
Node ablation: remove nodes (and their incident edges) to simulate
road closures due to flooding, accidents, or construction.
"""
import logging
from typing import List

import networkx as nx

logger = logging.getLogger(__name__)


def ablate_nodes(G: nx.Graph, node_ids: List) -> nx.Graph:
    """
    Return a copy of G with the specified nodes (and all incident edges) removed.

    Args:
        G:        Original road graph.
        node_ids: List of node identifiers to ablate.

    Returns:
        Perturbed graph (copy — original is preserved).
    """
    perturbed = G.copy()
    if "is_osm_fallback" in perturbed.graph:
        del perturbed.graph["is_osm_fallback"]
    valid_nodes = [n for n in node_ids if n in perturbed]
    invalid = [n for n in node_ids if n not in perturbed]

    if invalid:
        logger.warning(f"ablate_nodes: {len(invalid)} node IDs not found in graph: {invalid[:5]}")

    perturbed.remove_nodes_from(valid_nodes)
    logger.info(f"Ablated {len(valid_nodes)} nodes. "
                f"Graph: {G.number_of_nodes()} → {perturbed.number_of_nodes()} nodes")
    return perturbed
