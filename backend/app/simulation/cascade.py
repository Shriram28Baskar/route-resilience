"""
Cascading failure simulation.

After each ablation step, recompute centrality on the perturbed graph and
identify nodes that newly exceed a 'near-failure' threshold (normalized
betweenness ≥ threshold × max_centrality). These are ablated in the next
iteration, modelling second-order congestion collapse.
"""
import logging
from typing import List, Dict

import networkx as nx

from app.graph_pipeline.centrality import compute_betweenness
from app.simulation.ablation import ablate_nodes

logger = logging.getLogger(__name__)


def run_cascade(
    G: nx.Graph,
    seed_nodes: List,
    max_iterations: int = 3,
    threshold: float = 0.7,
) -> List[Dict]:
    """
    Run iterative cascading failure simulation.

    Args:
        G:              Original graph.
        seed_nodes:     Initial ablation targets.
        max_iterations: Maximum cascade steps.
        threshold:      Fraction of max centrality above which a node is
                        considered 'near failure' in the next iteration.

    Returns:
        List of step dicts:
        [
          { "iteration": 0, "ablated": [...], "newly_stressed": [...],
            "component_count": int, "lcc_size": int },
          ...
        ]
    """
    steps = []
    current_G = G.copy()
    current_ablated = list(seed_nodes)

    for iteration in range(max_iterations):
        current_G = ablate_nodes(current_G, current_ablated)

        components = list(nx.connected_components(current_G))
        lcc_size = max((len(c) for c in components), default=0)

        if current_G.number_of_nodes() < 2:
            steps.append({
                "iteration": iteration,
                "ablated": [str(n) for n in current_ablated],
                "newly_stressed": [],
                "component_count": len(components),
                "lcc_size": lcc_size,
                "note": "Graph too small to continue cascade",
            })
            break

        # Recompute centrality on the perturbed graph
        centrality = compute_betweenness(current_G, k=min(100, current_G.number_of_nodes()))
        max_score = max(centrality.values(), default=0)

        newly_stressed = [
            {
                "node_id": str(nid),
                "centrality": round(score, 4),
                "x": current_G.nodes[nid].get("x", 0),
                "y": current_G.nodes[nid].get("y", 0),
            }
            for nid, score in centrality.items()
            if score >= threshold * max_score and max_score > 0
        ]

        steps.append({
            "iteration": iteration,
            "ablated": [str(n) for n in current_ablated],
            "newly_stressed": newly_stressed,
            "component_count": len(components),
            "lcc_size": lcc_size,
        })

        logger.info(f"Cascade iteration {iteration}: ablated={len(current_ablated)}, "
                    f"stressed={len(newly_stressed)}, components={len(components)}")

        # Next iteration ablates the newly stressed nodes
        current_ablated = [nid for item in newly_stressed for nid, _ in [(item["node_id"], None)]
                           if nid in {str(n) for n in current_G.nodes()}]
        # Resolve string IDs back to graph node keys
        node_map = {str(n): n for n in current_G.nodes()}
        current_ablated = [node_map[sid] for sid in [item["node_id"] for item in newly_stressed]
                           if sid in node_map]

        if not current_ablated:
            logger.info("No new stressed nodes — cascade stabilised.")
            break

    return steps
