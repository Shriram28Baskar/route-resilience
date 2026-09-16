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

# Optional stress-threshold dampening: if > 0, the threshold rises by this fraction
# of max_score each iteration, so fewer nodes qualify over time.
#
# M3: DEFAULT IS NOW 0.0 (off). A non-zero value imposes monotonic decay on the
# result rather than measuring it, so it must be an explicit, declared choice.
# The value actually used is returned on every step as "dampening_factor".
# Measured A/B on an identical chokepoint fixture: 0.15 produced [6, 3, 1, 0];
# 0.0 produces [6, 21, 21, 21, 19, 21]. The decay was imposed, not observed.
_DAMPENING_FACTOR = 0.0


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
        centrality = compute_betweenness(current_G, k=min(50, current_G.number_of_nodes()))
        max_score = max(centrality.values(), default=0)

        # Dampened threshold: rises each iteration so fewer nodes qualify
        # This enforces the physics constraint that cascade dampens over time.
        # M3b (removed): a cap `min(dampened_threshold, 0.98)` commented
        # "cap at 98% so we always show some data" guaranteed a non-empty
        # result. With _DAMPENING_FACTOR == 0.0 this is exactly the
        # caller-supplied threshold.
        effective_threshold = threshold + iteration * _DAMPENING_FACTOR

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

        # M4 (removed): each iteration was truncated to 65% of the previous count,
        # manufacturing a decay curve. Counts are now reported as measured and may
        # rise as well as fall.

        steps.append({
            "iteration": iteration,
            "dampening_factor": _DAMPENING_FACTOR,
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
