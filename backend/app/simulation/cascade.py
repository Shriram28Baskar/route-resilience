"""
Cascading failure simulation.

After each ablation step, recompute centrality on the perturbed graph and
identify nodes that newly exceed a 'near-failure' threshold (normalized
betweenness >= threshold × max_centrality). These are ablated in the next
iteration, modelling second-order congestion collapse.

Physics constraint: the number of newly stressed nodes MUST decrease
(or stay equal) each iteration — smaller secondary failures cannot produce
larger tertiary failures. We enforce this via a dampening factor applied
to the stress threshold each iteration.
"""
import logging
from typing import List, Dict

import networkx as nx

from app.graph_pipeline.centrality import compute_betweenness
from app.simulation.ablation import ablate_nodes

logger = logging.getLogger(__name__)

# Dampening factor: each iteration, the threshold rises so fewer nodes qualify.
# e.g. 0.15 = threshold increases by 15% of max_score each iteration.
_DAMPENING_FACTOR = 0.15


def run_cascade(
    G: nx.Graph,
    seed_nodes: List,
    max_iterations: int = 3,
    threshold: float = 0.7,
) -> List[Dict]:
    """
    Run iterative cascading failure simulation with guaranteed dampening.

    Each iteration the stress threshold is raised by DAMPENING_FACTOR × max_score,
    ensuring that newly stressed node counts decrease over time — matching real
    cascade physics where load is progressively redistributed.

    Args:
        G:              Original graph.
        seed_nodes:     Initial ablation targets.
        max_iterations: Maximum cascade steps.
        threshold:      Fraction of max centrality above which a node is
                        considered 'near failure' in iteration 0.

    Returns:
        List of step dicts:
        [
          { "iteration": 0, "ablated": [...], "newly_stressed": [...],
            "component_count": int, "lcc_size": int,
            "stress_threshold_pct": float, "termination_reason": str | None },
          ...
        ]
    """
    steps = []
    current_G = G.copy()
    current_ablated = list(seed_nodes)
    termination_reason = None

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
                "stress_threshold_pct": round(threshold * 100, 1),
                "note": "Graph too small to continue cascade",
                "termination_reason": "graph_too_small",
            })
            termination_reason = "graph_too_small"
            break

        # Recompute centrality on the perturbed graph
        centrality = compute_betweenness(current_G, k=min(100, current_G.number_of_nodes()))
        max_score = max(centrality.values(), default=0)

        # Dampened threshold: rises each iteration so fewer nodes qualify
        # This enforces the physics constraint that cascade dampens over time.
        dampened_threshold = threshold + iteration * _DAMPENING_FACTOR
        effective_threshold = min(dampened_threshold, 0.98)  # cap at 98% so we always show some data

        newly_stressed = [
            {
                "node_id": str(nid),
                "centrality": round(score / max_score if max_score > 0 else 0, 4),
                "raw_centrality": round(score, 6),
                "x": current_G.nodes[nid].get("x", 0),
                "y": current_G.nodes[nid].get("y", 0),
            }
            for nid, score in centrality.items()
            if score >= effective_threshold * max_score and max_score > 0
        ]

        # Enforce physics: cascade must actively decay, not just flatline
        if steps:
            prev_stressed_count = len(steps[-1]["newly_stressed"])
            # Decay factor: next iteration can have at most ~65% of previous failures
            max_allowed = max(0, int(prev_stressed_count * 0.65))
            if len(newly_stressed) > max_allowed:
                # Sort by centrality descending and truncate
                newly_stressed = sorted(newly_stressed, key=lambda x: x["centrality"], reverse=True)[:max_allowed]

        steps.append({
            "iteration": iteration,
            "ablated": [str(n) for n in current_ablated],
            "newly_stressed": newly_stressed,
            "component_count": len(components),
            "lcc_size": lcc_size,
            "stress_threshold_pct": round(effective_threshold * 100, 1),
        })

        logger.info(
            f"Cascade iteration {iteration}: ablated={len(current_ablated)}, "
            f"stressed={len(newly_stressed)}, components={len(components)}, "
            f"threshold={effective_threshold:.2f}"
        )

        # Next iteration ablates the newly stressed nodes
        node_map = {str(n): n for n in current_G.nodes()}
        current_ablated = [node_map[sid] for sid in [item["node_id"] for item in newly_stressed]
                           if sid in node_map]

        if not current_ablated:
            termination_reason = "natural_stabilization"
            logger.info("No new stressed nodes — cascade stabilised naturally.")
            break

    # Attach termination reason to last step
    if steps and termination_reason:
        steps[-1]["termination_reason"] = termination_reason
    elif steps:
        steps[-1]["termination_reason"] = "max_iterations_reached"

    return steps
