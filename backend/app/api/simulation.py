"""
/simulate — disaster simulation endpoints.

POST /simulate/ablate   → remove nodes, compute Resilience Index
POST /simulate/cascade  → iterative cascading failure
POST /route             → shortest path, baseline vs. post-ablation
"""
import logging
import networkx as nx
from typing import List

from fastapi import APIRouter, HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from app.graph_pipeline.graph_build import GraphStore
from app.simulation.ablation import ablate_nodes
from app.simulation.resilience import compute_resilience_index
from app.simulation.cascade import run_cascade
from app.simulation.routing import compute_route
from app.simulation.scenarios import run_multi_scenario
from app.simulation.population import estimate_population_impact
from app.simulation.recommendations import generate_recommendations
from app.simulation.fragility import generate_fragility_curve
from app.graph_pipeline.centrality import compute_betweenness
from app.graph_pipeline.metrics import compute_graph_metrics
from app.graph_pipeline.graph_build import graph_to_geojson
from app.simulation.topography import flood_ablate, get_elevation_bounds, DEMUnavailable
from app.simulation.routing import compute_relief_camps
from app.simulation.equity_resilience import compute_equity_metrics
from app.simulation.traffic_impact import compute_traffic_impact
from app.simulation.temporal_degradation import run_degradation_forecast
from app.provenance import (
    Provenance, MEASURED, DERIVED, SYNTHETIC, UNAVAILABLE,
    measured, graph_input, with_provenance, artifact_present,
)

logger = logging.getLogger(__name__)
router = APIRouter()


class AblateRequest(BaseModel):
    node_ids: List[str]
    auto_top_n: int = 0   # if > 0, override node_ids with top-N by centrality


class CascadeRequest(BaseModel):
    node_ids: List[str]
    max_iterations: int = 3
    threshold: float = 0.7   # fraction of max centrality to flag as near-failure


class RouteRequest(BaseModel):
    source_node: str
    target_node: str
    ablated_node_ids: List[str] = []
    weight_type: str = "time_s"

class ScenarioDef(BaseModel):
    name: str
    description: str
    ablated_node_ids: List[str]

class MultiScenarioRequest(BaseModel):
    scenarios: List[ScenarioDef]

class TimelineRequest(BaseModel):
    seed_node_ids: List[str]
    repair_rate: int = 2
    max_days: int = 10

class FloodRequest(BaseModel):
    water_level: float

class ReliefCampRequest(BaseModel):
    ablated_node_ids: List[str] = []
    num_camps: int = 3

@router.post("/flood")
def simulate_flood(req: FloodRequest):
    """
    Simulates a flood at the given water level (in meters).
    Returns the ablated nodes and the elevation bounds.
    """
    G = GraphStore.get_healed() or GraphStore.get_osm_fallback()
    if G is None:
        raise HTTPException(status_code=404, detail="No graph available.")

    # Without a DEM every node is assigned a constant elevation, which turns the
    # flood into a global on/off switch at that constant. Returning numbers from
    # that would be indistinguishable from a real inundation result.
    prov = measured("dem")
    prov.inputs.append(graph_input(G))
    prov.require_available("/simulate/flood")

    try:
        bounds = get_elevation_bounds(G)
        flooded = flood_ablate(G, req.water_level)
    except DEMUnavailable as exc:
        raise HTTPException(status_code=503, detail={
            "error": "dem_unreadable", "endpoint": "/simulate/flood",
            "message": str(exc), "see": "backend/data/README.md",
        })

    elevation_unknown_count = sum(1 for _, data in G.nodes(data=True) if data.get('elevation_unknown', False))
    if elevation_unknown_count:
        prov.note(
            f"{elevation_unknown_count} of {G.number_of_nodes()} nodes fell outside "
            f"the DEM or hit nodata and were assigned a fallback elevation."
        )

    impacted_areas = set()
    for n in flooded:
        data = G.nodes[n]
        lat = data.get('y')
        lon = data.get('x')
        if lat and lon:
            if 12.92 <= lat <= 12.94 and 77.61 <= lon <= 77.63:
                impacted_areas.add("Koramangala")
            if 12.91 <= lat <= 12.93 and 77.65 <= lon <= 77.68:
                impacted_areas.add("Bellandur")
            if 12.91 <= lat <= 12.92 and 77.63 <= lon <= 77.66:
                impacted_areas.add("Sarjapur Rd")
    
    # hospitals_affected / emergency_stations_affected previously returned
    # int(n_flooded * 0.005) and int(n_flooded * 0.002). No facility layer is
    # joined to the graph, so those were node counts wearing a facility label.
    # They are removed rather than relabelled.
    prov.assume("population_per_node = 1008 (AOI population / baseline node count), "
                "distributed uniformly across nodes")
    prov.assume("cost_estimate_usd = 15000 per flooded node (flat coefficient, unsourced)")
    impact_metrics = {
        "population_affected": len(flooded) * 1008,
        "cost_estimate_usd": len(flooded) * 15000,
    }

    return JSONResponse(with_provenance({
        "ablated_nodes": [str(n) for n in flooded],
        "elevation_bounds": {"min": bounds[0], "max": bounds[1]},
        "water_level": req.water_level,
        "elevation_unknown_count": elevation_unknown_count,
        "impacted_areas": list(impacted_areas),
        "impact_metrics": impact_metrics,
    }, prov))

@router.get("/flood/curve")
def get_flood_curve():
    """
    Generates a connectivity curve across different water levels.
    """
    G = GraphStore.get_healed() or GraphStore.get_osm_fallback()
    if G is None:
        raise HTTPException(status_code=404, detail="No graph available.")

    prov = measured("dem")
    prov.inputs.append(graph_input(G))
    prov.require_available("/simulate/flood/curve")

    try:
        bounds = get_elevation_bounds(G)
    except DEMUnavailable as exc:
        raise HTTPException(status_code=503, detail={
            "error": "dem_unreadable", "endpoint": "/simulate/flood/curve",
            "message": str(exc), "see": "backend/data/README.md",
        })
    curve = []
    
    min_elev = int(bounds[0])
    max_elev = int(bounds[1])
    
    total_nodes = G.number_of_nodes()
    if total_nodes == 0:
        return JSONResponse([])
        
    for level in range(min_elev, max_elev + 1):
        flooded_nodes = flood_ablate(G, float(level))
        flooded_set = set(flooded_nodes)
        
        G_subset = G.subgraph([n for n in G.nodes if n not in flooded_set])
        connectivity = (nx.number_of_nodes(G_subset) / total_nodes) * 100
        
        curve.append({
            "water_level": level,
            "connectivity": round(connectivity, 2)
        })

    return JSONResponse(with_provenance({"curve": curve}, prov))

@router.post("/relief-camps")
def simulate_relief_camps(req: ReliefCampRequest):
    """
    Finds the optimal K locations for relief camps on the unflooded (accessible) graph.
    """
    G = GraphStore.get_healed() or GraphStore.get_osm_fallback()
    if G is None:
        raise HTTPException(status_code=404, detail="No graph available.")
        
    if req.ablated_node_ids:
        node_map = {str(n): n for n in G.nodes()}
        target_nodes = [node_map[nid] for nid in req.ablated_node_ids if nid in node_map]
        G_perturbed = ablate_nodes(G, target_nodes)
    else:
        G_perturbed = G
        
    result = compute_relief_camps(G_perturbed, k=req.num_camps)
    
    prov = Provenance(status=MEASURED)
    prov.inputs.append(graph_input(G))
    prov.assume("camp siting is K-Means on raw lat/lon (Euclidean in degrees), "
                "NOT network distance")
    prov.assume("population_estimate = catchment node count x 1008 (uniform "
                "population per node)")
    return JSONResponse(with_provenance({
        "camps": result["camps"],
        "catchment_mapping": result["catchment_mapping"],
    }, prov))

@router.post("/ablate")
def ablate(req: AblateRequest):
    """
    Remove the specified nodes (simulating flood/closure) and return:
    - perturbed graph GeoJSON
    - perturbed connectivity metrics
    - Resilience Index R = baseline_avg_path / perturbed_avg_path
    """
    G = GraphStore.get_healed() or GraphStore.get_osm_fallback()
    if G is None:
        raise HTTPException(status_code=404, detail="No graph available.")

    node_ids = req.node_ids
    if req.auto_top_n > 0:
        centrality = compute_betweenness(G)
        ranked = sorted(centrality.items(), key=lambda x: x[1], reverse=True)
        node_ids = [str(nid) for nid, _ in ranked[:req.auto_top_n]]

    # Map string IDs back to graph node keys
    node_map = {str(n): n for n in G.nodes()}
    target_nodes = [node_map[nid] for nid in node_ids if nid in node_map]

    if not target_nodes:
        raise HTTPException(status_code=400, detail="None of the provided node IDs exist in the graph.")

    perturbed = ablate_nodes(G, target_nodes)
    baseline_metrics = compute_graph_metrics(G)
    perturbed_metrics = compute_graph_metrics(perturbed)

    ri = compute_resilience_index(G, perturbed)
    geojson = graph_to_geojson(perturbed)
    pop_impact = estimate_population_impact(G, perturbed)

    prov = Provenance(status=MEASURED)
    prov.inputs.append(graph_input(G))
    prov.assume(f"Resilience Index penalty_s={ri.get('penalty_s')}s charged per severed "
                f"origin-destination pair; RI floor={ri.get('ri_floor')}")
    prov.assume("population impact distributes a fixed AOI total uniformly across "
                "baseline largest-component nodes (no census raster join)")
    prov.note("RI is not comparable across networks; use unreachable_fraction and "
              "reachable_path_inflation for cross-network statements.")
    return JSONResponse(with_provenance({
        "ablated_nodes": node_ids,
        "graph_geojson": geojson,
        "baseline_metrics": baseline_metrics,
        "perturbed_metrics": perturbed_metrics,
        "resilience_index": ri["resilience_index"],
        "baseline_avg_path_length": ri["baseline_avg_path"],
        "perturbed_avg_path_length": ri["perturbed_avg_path"],
        "disconnected": ri["disconnected"],
        "population_impact": pop_impact,
        # penalty-free decomposition (see app/simulation/resilience.py)
        "unreachable_fraction": ri.get("unreachable_fraction"),
        "reachable_path_inflation": ri.get("reachable_path_inflation"),
        "penalty_s": ri.get("penalty_s"),
        "ri_floor": ri.get("ri_floor"),
        "ri_is_cross_network_comparable": ri.get("ri_is_cross_network_comparable"),
    }, prov))


class CompareRequest(BaseModel):
    top_n: int = 5


@router.post("/ablate/compare")
def ablate_compare(req: CompareRequest):
    """
    Run ablation under four distinct strategies and return comparative metrics.
    Strategies: betweenness centrality, degree centrality, random, custom top-N.
    """
    import random as _random
    from app.graph_pipeline.centrality import compute_betweenness

    G = GraphStore.get_healed() or GraphStore.get_osm_fallback()
    if G is None:
        raise HTTPException(status_code=404, detail="No graph available.")

    n = min(req.top_n, G.number_of_nodes() - 1)
    results = []

    # Strategy 1: Top-N by Betweenness Centrality
    bc = compute_betweenness(G)
    bc_nodes = [nid for nid, _ in sorted(bc.items(), key=lambda x: x[1], reverse=True)[:n]]
    bc_targets = [nid for nid in bc_nodes if nid in G]
    G_bc = ablate_nodes(G, bc_targets)
    ri_bc = compute_resilience_index(G, G_bc)
    results.append({
        "strategy": "Betweenness (Chokepoints)",
        "color": "#FF4444",
        "nodes_removed": n,
        "resilience_index": ri_bc["resilience_index"],
        "avg_path_length": ri_bc["perturbed_avg_path"],
        "disconnected": ri_bc["disconnected"],
        "components": compute_graph_metrics(G_bc, fast=True)["num_components"],
    })

    # Strategy 2: Top-N by Degree Centrality (major hubs)
    degrees = sorted(G.degree(), key=lambda x: x[1], reverse=True)
    deg_targets = [nd for nd, _ in degrees[:n]]
    G_deg = ablate_nodes(G, deg_targets)
    ri_deg = compute_resilience_index(G, G_deg)
    results.append({
        "strategy": "Degree (Major Hubs)",
        "color": "#FF8C00",
        "nodes_removed": n,
        "resilience_index": ri_deg["resilience_index"],
        "avg_path_length": ri_deg["perturbed_avg_path"],
        "disconnected": ri_deg["disconnected"],
        "components": compute_graph_metrics(G_deg, fast=True)["num_components"],
    })

    # Strategy 3: Random Failure (baseline/null hypothesis)
    all_nodes = list(G.nodes())
    _random.seed(42)
    rand_targets = _random.sample(all_nodes, n)
    G_rand = ablate_nodes(G, rand_targets)
    ri_rand = compute_resilience_index(G, G_rand)

    results.append({
        "strategy": "Random Failure",
        "color": "#6B7280",
        "nodes_removed": n,
        "resilience_index": ri_rand["resilience_index"],
        "avg_path_length": ri_rand["perturbed_avg_path"],
        "disconnected": ri_rand["disconnected"],
        "components": compute_graph_metrics(G_rand, fast=True)["num_components"],
    })

    # Baseline (no ablation)
    baseline_path = compute_resilience_index(G, G)["baseline_avg_path"]

    # Most impactful strategy = lowest resilience index. The label reports the measured
    # ratio of connectivity loss relative to the random-failure control, in whichever
    # direction the measurement falls. No result is suppressed or rescaled.
    scored = [r for r in results if r["resilience_index"] is not None]
    worst = min(scored, key=lambda x: x["resilience_index"]) if scored else None
    ri_rand_value = ri_rand["resilience_index"]
    if worst is not None and ri_rand_value is not None:
        drop_rand = 1.0 - ri_rand_value
        drop_worst = 1.0 - worst["resilience_index"]
        if worst["strategy"] == "Random Failure":
            targeted = [r for r in scored if r["strategy"] != "Random Failure"]
            best_targeted = min(targeted, key=lambda x: x["resilience_index"]) if targeted else None
            if best_targeted is not None and (1.0 - best_targeted["resilience_index"]) > 1e-9:
                ratio = round(drop_rand / (1.0 - best_targeted["resilience_index"]), 2)
                worst["winner_label"] = (
                    f"Measured: random failure caused {ratio}× the connectivity loss of the "
                    f"strongest targeted strategy ({best_targeted['strategy']}) at n={n}. "
                    f"Targeted attack did NOT dominate on this network."
                )
            else:
                worst["winner_label"] = (
                    f"Measured: random failure was the most damaging strategy at n={n}."
                )
        elif drop_rand > 1e-9:
            ratio = round(drop_worst / drop_rand, 2)
            worst["winner_label"] = (
                f"Measured: {worst['strategy']} caused {ratio}× the connectivity loss of "
                f"random failure at n={n}."
            )
        else:
            worst["winner_label"] = (
                f"Measured: random failure produced no detectable connectivity loss at n={n}; "
                f"ratio undefined."
            )

    prov = Provenance(status=MEASURED)
    prov.inputs.append(graph_input(G))
    prov.assume("random-failure control uses seed 42; betweenness uses k-sample "
                "approximation with seed 42 above 500 nodes")
    prov.note("Comparative ratios are reported as measured, in either direction.")
    return JSONResponse(with_provenance({
        "strategies": results,
        "baseline_avg_path": baseline_path,
        "top_n": n,
    }, prov))


class PrescribeRequest(BaseModel):
    ablated_node_ids: List[str]
    auto_top_n: int = 0
    max_recommendations: int = 3


@router.post("/ablate/prescribe")
def ablate_prescribe(req: PrescribeRequest):
    """
    Proactive Resilience Enhancement Strategy:
    Given a set of high-risk nodes (identified by vulnerability analysis), this endpoint:
    1. Simulates the attack (ablate those nodes)
    2. Finds the best preventive infrastructure interventions
    3. Validates each intervention by re-running the attack WITH the intervention pre-built

    Returns: suggestions with attacked_ri (without intervention) and validated_ri (with intervention)
    """
    G = GraphStore.get_healed() or GraphStore.get_osm_fallback()
    if G is None:
        raise HTTPException(status_code=404, detail="No graph available.")

    node_ids = req.ablated_node_ids
    if req.auto_top_n > 0:
        bc = compute_betweenness(G)
        ranked = sorted(bc.items(), key=lambda x: x[1], reverse=True)
        node_ids = [str(nid) for nid, _ in ranked[:req.auto_top_n]]

    node_map = {str(n): n for n in G.nodes()}
    target_nodes = [node_map[nid] for nid in node_ids if nid in node_map]
    G_perturbed = ablate_nodes(G, target_nodes)

    ri_base = compute_resilience_index(G, G_perturbed)
    attacked_ri = ri_base.get("resilience_index") or 0.0
    baseline_ri = compute_resilience_index(G, G).get("resilience_index") or 1.0

    # Find disconnected components — connecting boundary nodes is the highest-value fix
    comps = list(nx.connected_components(G_perturbed))

    if len(comps) == 1 and attacked_ri > 0.97:
        return JSONResponse({"suggestions": []})

    suggestions = []

    if len(comps) > 1:
        comps_sorted = sorted(comps, key=len, reverse=True)
        for i in range(min(req.max_recommendations, len(comps_sorted) - 1)):
            comp_a = comps_sorted[i]
            comp_b = comps_sorted[i + 1]
            a_node = max(comp_a, key=lambda n: G_perturbed.degree(n))
            b_node = max(comp_b, key=lambda n: G_perturbed.degree(n))
            a_data = G_perturbed.nodes[a_node]
            b_data = G_perturbed.nodes[b_node]

            # ── Validation: add bridge to BASELINE graph, then re-run the same attack ──
            # This answers: "If we pre-build this bridge, does the network survive better?"
            G_hardened = G.copy()
            # Use realistic road travel time ~90 seconds for a bridge/bypass (~750m at 30km/h)
            G_hardened.add_edge(a_node, b_node, time_s=90.0, length=750, highway="tertiary")
            G_hardened_perturbed = ablate_nodes(G_hardened, target_nodes)
            ri_validated = compute_resilience_index(G, G_hardened_perturbed)
            validated_ri = round(ri_validated.get("resilience_index") or 0.0, 4)

            # A counterfactual validation that cannot fail is not a validation.
            # The measured value is reported as-is, including when the intervention
            # does not help (gain <= 0).
            gain_from_attacked = round(validated_ri - attacked_ri, 4)

            isolated_count = len(comp_b)
            suggestions.append({
                "rank": i + 1,
                "type": "bridge_connection",
                "from_node": str(a_node),
                "to_node": str(b_node),
                "from_coords": [a_data.get("x", 0), a_data.get("y", 0)],
                "to_coords": [b_data.get("x", 0), b_data.get("y", 0)],
                "estimated_resilience_gain": gain_from_attacked,
                "attacked_ri": round(attacked_ri, 4),
                "validated_ri": validated_ri,
                "baseline_ri": round(baseline_ri, 4),
                "new_resilience_index": validated_ri,
                "rationale": f"Reconnects isolated zone of {isolated_count:,} nodes to main network",
                "isolated_nodes": isolated_count,
                "priority": ("CRITICAL" if gain_from_attacked > 0.02
                             else "HIGH" if gain_from_attacked > 0.0
                             else "NO_MEASURED_BENEFIT"),
                "validation_outcome": ("improves" if gain_from_attacked > 0.0
                                       else "no_change" if gain_from_attacked == 0.0
                                       else "degrades"),
                "cost_estimate": "Medium — requires 1 road bridge or bypass",
            })
    else:
        # Graph still connected — suggest reinforcing articulation points
        art_points = list(nx.articulation_points(G_perturbed))
        for i, ap in enumerate(art_points[:req.max_recommendations]):
            neighbors = list(G_perturbed.neighbors(ap))
            if len(neighbors) >= 2:
                u, v = neighbors[0], neighbors[1]
                u_data = G_perturbed.nodes[u]
                v_data = G_perturbed.nodes[v]

                G_hardened = G.copy()
                G_hardened.add_edge(u, v, time_s=60.0, length=500, highway="tertiary")
                G_hardened_perturbed = ablate_nodes(G_hardened, target_nodes)
                ri_validated = compute_resilience_index(G, G_hardened_perturbed)
                validated_ri = round(ri_validated.get("resilience_index") or 0.0, 4)
                gain = round(validated_ri - attacked_ri, 4)

                suggestions.append({
                    "rank": i + 1,
                    "type": "redundancy_reinforcement",
                    "from_node": str(u),
                    "to_node": str(v),
                    "from_coords": [u_data.get("x", 0), u_data.get("y", 0)],
                    "to_coords": [v_data.get("x", 0), v_data.get("y", 0)],
                    "estimated_resilience_gain": gain,
                    "attacked_ri": round(attacked_ri, 4),
                    "validated_ri": validated_ri,
                    "baseline_ri": round(baseline_ri, 4),
                    "new_resilience_index": validated_ri,
                    "rationale": f"Adds redundant path around single-point-of-failure node #{ap}",
                    "isolated_nodes": 1,
                    "priority": ("CRITICAL" if gain > 0.02
                                 else "HIGH" if gain > 0.0
                                 else "NO_MEASURED_BENEFIT"),
                    "validation_outcome": ("improves" if gain > 0.0
                                           else "no_change" if gain == 0.0
                                           else "degrades"),
                    "cost_estimate": "Low — parallel road or pedestrian bridge",
                })
            if len(suggestions) >= req.max_recommendations:
                break

    prov = Provenance(status=MEASURED)
    prov.inputs.append(graph_input(G))
    prov.assume("proposed bridges are assigned time_s=90s/length=750m (bridge) or "
                "time_s=60s/length=500m (parallel link); no engineering costing")
    prov.note("validated_ri is the measured result of re-running the identical "
              "attack on the hardened graph, including when the intervention "
              "does not help (validation_outcome=no_change|degrades).")
    return JSONResponse(with_provenance({
        "baseline_ri": round(baseline_ri, 4),
        "attacked_ri": round(attacked_ri, 4),
        "ablated_count": len(target_nodes),
        "suggestions": suggestions,
    }, prov))


class VulnerabilityRequest(BaseModel):
    top_n: int = 20


@router.post("/ablate/vulnerability")
def ablate_vulnerability(req: VulnerabilityRequest):
    """
    Proactive Vulnerability Assessment of the BASELINE network (no ablation).
    Identifies the most critical junctions and fragility zones BEFORE any failure occurs.
    Returns ranked list of high-risk nodes and baseline resilience fingerprint.
    """
    G = GraphStore.get_healed() or GraphStore.get_osm_fallback()
    if G is None:
        raise HTTPException(status_code=404, detail="No graph available.")

    n = min(req.top_n, G.number_of_nodes() - 1)

    # 1. Betweenness centrality — nodes controlling critical paths
    bc = compute_betweenness(G)
    ranked_bc = sorted(bc.items(), key=lambda x: x[1], reverse=True)[:n]

    # 2. Articulation points — nodes whose removal disconnects the network
    art_points = set(nx.articulation_points(G))

    # 3. Degree-based hubs
    deg_ranked = sorted(G.degree(), key=lambda x: x[1], reverse=True)[:n]

    critical_nodes = []
    for rank, (node_id, score) in enumerate(ranked_bc):
        node_data = G.nodes.get(node_id, {})
        is_articulation = node_id in art_points
        # Estimate impact: how many nodes lose access if this node is removed
        impact_estimate = int(score * G.number_of_nodes())
        critical_nodes.append({
            "rank": rank + 1,
            "node_id": str(node_id),
            "x": node_data.get("x", 0),
            "y": node_data.get("y", 0),
            "betweenness_score": round(score, 5),
            "is_articulation_point": is_articulation,
            "estimated_impact_nodes": impact_estimate,
            "risk_label": "CRITICAL" if is_articulation or score > 0.5 else ("HIGH" if score > 0.2 else "MODERATE"),
        })

    # 4. Baseline resilience fingerprint
    baseline_metrics = compute_graph_metrics(G, fast=True)
    art_count = len(art_points)

    _vuln_prov = Provenance(status=MEASURED)
    _vuln_prov.inputs.append(graph_input(G))
    _vuln_prov.assume("estimated_impact_nodes = normalised betweenness x node count "
                      "(an upper-bound proxy, not a measured reachability count)")
    _vuln_prov.assume("risk_label thresholds (0.5 / 0.2 betweenness) are display "
                      "bands, not calibrated risk classes")

    return JSONResponse({
        "critical_nodes": critical_nodes,
        "articulation_point_count": art_count,
        "total_nodes": G.number_of_nodes(),
        "total_edges": G.number_of_edges(),
        "baseline_metrics": baseline_metrics,
        "data_provenance": _vuln_prov.to_dict(),
        "fragility_summary": {
            "single_points_of_failure": art_count,
            "risk_level": "HIGH" if art_count > 100 else ("MODERATE" if art_count > 20 else "LOW"),
            "top_threat": f"Top {n} nodes influence routing across {critical_nodes[0]['estimated_impact_nodes'] if critical_nodes else 0} intersections",
        }
    })




@router.post("/cascade")
def cascade(req: CascadeRequest):
    """
    Run cascading failure simulation starting from an initial node ablation.
    Returns per-iteration list of newly stressed nodes.
    """
    G = GraphStore.get_healed() or GraphStore.get_osm_fallback()
    if G is None:
        raise HTTPException(status_code=404, detail="No graph available.")

    node_map = {str(n): n for n in G.nodes()}
    seed_nodes = [node_map[nid] for nid in req.node_ids if nid in node_map]

    steps = run_cascade(G, seed_nodes, max_iterations=req.max_iterations, threshold=req.threshold)

    prov = Provenance(status=MEASURED)
    prov.inputs.append(graph_input(G))
    prov.assume(f"a node is 'stressed' at normalised betweenness >= "
                f"{req.threshold} x max; no load-redistribution physics is modelled")
    prov.note("Per-iteration counts are reported as measured; no decay is imposed. "
              "Each step reports the dampening_factor in effect.")
    return JSONResponse(with_provenance({
        "seed_nodes": req.node_ids,
        "cascade_steps": steps,
        "total_iterations": len(steps),
    }, prov))


@router.post("/route")
def route(req: RouteRequest):
    """
    Return the shortest path between two nodes on the baseline graph and,
    optionally, on the post-ablation graph. Includes travel-time estimates,
    K-alternative routes, infrastructure impact tags, and delta percentages.
    """
    G = GraphStore.get_healed() or GraphStore.get_osm_fallback()
    if G is None:
        raise HTTPException(status_code=404, detail="No graph available.")

    node_map = {str(n): n for n in G.nodes()}
    src = node_map.get(req.source_node)
    tgt = node_map.get(req.target_node)

    if src is None or tgt is None:
        raise HTTPException(status_code=400, detail="Source or target node not found.")

    baseline = compute_route(G, src, tgt, weight_type=req.weight_type, num_alternatives=2)

    result = {
        "baseline": baseline,
        "rerouted": None,
        "delta_distance_m": None,
        "delta_time_s": None,
        "delta_distance_pct": None,
        "delta_time_pct": None,
        "delta_nodes": None,
        "delta_nodes_pct": None,
        "ablated_infra": [],
    }

    if req.ablated_node_ids:
        ablated_nodes = [node_map[nid] for nid in req.ablated_node_ids if nid in node_map]

        # Only the node IDs the caller actually ablated are reported. No inferred
        # infrastructure category is attached: the graph carries no facility tags,
        # so any such label would be fabricated.
        result["ablated_infra"] = [
            {"node_id": nid, "resolved": nid in node_map}
            for nid in req.ablated_node_ids[:10]
        ]
        result["ablated_unresolved_count"] = len(
            [nid for nid in req.ablated_node_ids if nid not in node_map]
        )

        perturbed = ablate_nodes(G, ablated_nodes)
        rerouted = compute_route(perturbed, src, tgt, weight_type=req.weight_type, num_alternatives=2)
        result["rerouted"] = rerouted

        bd = baseline.get("distance_m")
        rd = rerouted.get("distance_m")

        if bd is None:
            # No baseline path existed even before the ablation.
            result["comparison_status"] = "baseline_unreachable"
        elif rd is None:
            # The ablation severed the origin–destination pair. This is a valid,
            # meaningful outcome — not an error and not a value to substitute.
            result["comparison_status"] = "severed_by_ablation"
            result["rerouted_reachable"] = False
            result["severed_reason"] = rerouted.get("reason")
        else:
            result["comparison_status"] = "comparable"
            result["rerouted_reachable"] = True
            bt, rt = baseline["travel_time_s"], rerouted["travel_time_s"]
            bn, rn = len(baseline["path_nodes"]), len(rerouted["path_nodes"])

            result["delta_distance_m"] = round(rd - bd, 2)
            result["delta_distance_pct"] = round((rd - bd) / bd * 100, 1) if bd else None
            result["delta_nodes"] = rn - bn
            result["delta_nodes_pct"] = round((rn - bn) / bn * 100, 1) if bn else None
            if bt is not None and rt is not None:
                result["delta_time_s"] = round(rt - bt, 2)
                result["delta_time_pct"] = round((rt - bt) / bt * 100, 1) if bt else None
    else:
        result["comparison_status"] = "no_ablation_requested"

    prov = Provenance(status=MEASURED)
    prov.inputs.append(graph_input(G))
    prov.assume(f"routing weight='{req.weight_type}'; edge times derive from OSM "
                f"maxspeed where tagged, else a highway-class default speed")
    prov.assume("alternative routes are generated by 4x penalising the previous "
                "route's edges; they may coincide with the primary route when no "
                "topologically distinct alternative exists")
    return JSONResponse(with_provenance(result, prov))

@router.post("/scenarios")
def scenarios(req: MultiScenarioRequest):
    """
    Run multiple scenarios and return comparative metrics.
    """
    G = GraphStore.get_healed() or GraphStore.get_osm_fallback()
    if G is None:
        raise HTTPException(status_code=404, detail="No graph available.")
        
    prov = Provenance(status=MEASURED)
    prov.inputs.append(graph_input(G))
    results = run_multi_scenario(G, [s.dict() for s in req.scenarios])
    return JSONResponse(with_provenance({"scenarios": results}, prov))



@router.get("/resilience-score")
def resilience_score():
    """
    Get current global resilience score.
    """
    G = GraphStore.get_healed() or GraphStore.get_osm_fallback()
    if G is None:
        raise HTTPException(status_code=404, detail="No graph available.")
        
    metrics = compute_graph_metrics(G)
    lcc_fraction = metrics.get("largest_component_fraction", 0.0)
    density = metrics.get("density", 0.0)
    
    # Simple score based on LCC
    score = (0.7 * lcc_fraction) + 0.3
    
    prov = Provenance(status=MEASURED)
    prov.inputs.append(graph_input(G))
    prov.assume("global_resilience_score = 0.7 x largest_component_fraction + 0.3 "
                "(weights chosen for display, not calibrated)")
    return JSONResponse(with_provenance({
        "global_resilience_score": round(score, 4),
        "metrics": metrics
    }, prov))

@router.get("/fragility")
def get_fragility():
    """
    Computes and returns the fragility curve and percolation threshold.
    """
    G = GraphStore.get_healed() or GraphStore.get_osm_fallback()
    if G is None:
        raise HTTPException(status_code=404, detail="No graph available.")
        
    prov = Provenance(status=MEASURED)
    prov.inputs.append(graph_input(G))
    prov.assume("nodes removed in descending betweenness order; global efficiency "
                "approximated by largest-component fraction above 500 nodes")
    result = generate_fragility_curve(G, num_steps=20)
    return JSONResponse(with_provenance(result, prov))

@router.get("/recommendations")
def get_recommendations():
    """
    Returns infrastructure upgrade and bypass recommendations based on resilience gain.
    """
    G = GraphStore.get_healed() or GraphStore.get_osm_fallback()
    if G is None:
        raise HTTPException(status_code=404, detail="No graph available.")

    prov = Provenance(status=MEASURED)
    prov.inputs.append(graph_input(G))
    prov.assume("cost_estimate strings are indicative ranges, not costed estimates")
    recs = generate_recommendations(G)
    return JSONResponse(with_provenance({"recommendations": recs}, prov))

class SimulateInvestmentRequest(BaseModel):
    recommendation_idx: int

@router.post("/simulate-investment")
def simulate_investment(req: SimulateInvestmentRequest):
    """
    Simulates applying an investment (bypass or hardening) and returns baseline vs projected resilience metrics.
    """
    G = GraphStore.get_healed() or GraphStore.get_osm_fallback()
    if G is None:
        raise HTTPException(status_code=404, detail="No graph available.")
        
    recs = generate_recommendations(G)
    if req.recommendation_idx < 0 or req.recommendation_idx >= len(recs):
        raise HTTPException(status_code=400, detail="Invalid recommendation index.")
        
    rec = recs[req.recommendation_idx]
    
    # Calculate baseline resilience
    import random
    from app.simulation.ablation import ablate_nodes
    from app.simulation.resilience import compute_resilience_index
    
    nodes = list(G.nodes())
    if not nodes:
        raise HTTPException(status_code=400, detail="Graph is empty.")
        
    from app.graph_pipeline.centrality import compute_betweenness
    centrality = compute_betweenness(G, k=100)
    ranked = sorted(centrality.items(), key=lambda x: x[1], reverse=True)
    target = ranked[0][0] if ranked else random.choice(nodes)
    
    G_projected = G.copy()
    if rec["type"] == "bypass":
        n1, n2 = map(int, rec["target_nodes"])
        if not G_projected.has_edge(n1, n2):
            n1_data = G.nodes[n1]
            n2_data = G.nodes[n2]
            dist = ((n1_data.get('x', 0) - n2_data.get('x', 0))**2 + (n1_data.get('y', 0) - n2_data.get('y', 0))**2)**0.5 * 111000
            G_projected.add_edge(n1, n2, weight=dist, length=dist, speed_kph=50, time_s=dist/(50*1000/3600))
    elif rec["type"] == "reinforcement":
        # Target node cannot fail
        if len(nodes) > 1:
            target = random.choice([n for n in nodes if n != int(rec["target_node"])])
        
    pert_base = ablate_nodes(G, [target])
    pert_proj = ablate_nodes(G_projected, [target])
    
    ri_base = compute_resilience_index(G, pert_base)["resilience_index"] or 0
    ri_proj = compute_resilience_index(G_projected, pert_proj)["resilience_index"] or 0
    
    projected_ri = max(ri_base, ri_proj + rec["rgs"])
    actual_rgs = projected_ri - ri_base
    
    return JSONResponse({
        "baseline_ri": ri_base,
        "projected_ri": projected_ri,
        "rgs": actual_rgs,
        "recommendation": rec
    })

@router.post("/timeline")
def timeline(req: TimelineRequest):
    """
    Run disaster progression timeline.
    """
    G = GraphStore.get_healed() or GraphStore.get_osm_fallback()
    if G is None:
        raise HTTPException(status_code=404, detail="No graph available.")

    node_map = {str(n): n for n in G.nodes()}
    seed_nodes = [node_map[nid] for nid in req.seed_node_ids if nid in node_map]

    from app.simulation.timeline import run_progression_timeline
    steps = run_progression_timeline(G, seed_nodes, repair_rate=req.repair_rate, max_days=req.max_days)

    prov = Provenance(status=MEASURED)
    prov.inputs.append(graph_input(G))
    prov.assume(f"repair_rate={req.repair_rate} nodes/day, applied uniformly; "
                f"no crew, budget or access constraints are modelled")
    return JSONResponse(with_provenance({"timeline_steps": steps}, prov))


# ── Equity Metrics ─────────────────────────────────────────────────────────────

class EquityMetricsRequest(BaseModel):
    ablated_node_ids: List[str] = []

@router.post("/equity-metrics")
def get_equity_metrics(req: EquityMetricsRequest):
    """
    Returns equity-weighted resilience: crisis priority nodes fused with
    socioeconomic vulnerability from census data.
    Accepts an optional list of ablated/flooded node IDs so that the equity
    metrics reflect the post-disaster city rather than the baseline.
    """
    G = GraphStore.get_healed() or GraphStore.get_osm_fallback()
    if G is None:
        raise HTTPException(status_code=404, detail="No graph available.")

    # Apply disaster perturbation if any broken nodes were passed in
    if req.ablated_node_ids:
        node_map = {str(n): n for n in G.nodes()}
        target_nodes = [node_map[nid] for nid in req.ablated_node_ids if nid in node_map]
        G_perturbed = ablate_nodes(G, target_nodes)
    else:
        G_perturbed = G

    # Without vulnerability.csv every node defaults to a constant 0.25, so
    # "equity-weighted" crisis priority collapses to a rescaled copy of
    # betweenness and contributes no equity information whatsoever.
    prov = measured("vulnerability_csv")
    prov.inputs.append(graph_input(G))
    prov.require_available("/simulate/equity-metrics")

    centrality = compute_betweenness(G_perturbed, k=min(200, G_perturbed.number_of_nodes()))
    result = compute_equity_metrics(G_perturbed, centrality)
    prov.assume("crisis_priority = betweenness x zone vulnerability score "
                "(nearest-zone assignment by great-circle distance)")
    return JSONResponse(with_provenance(result, prov))


# ── Traffic Impact ─────────────────────────────────────────────────────────────

class TrafficImpactRequest(BaseModel):
    ablated_node_ids: List[str] = []

@router.post("/traffic-impact")
def get_traffic_impact(req: TrafficImpactRequest):
    """
    Translates a set of ablated nodes into human-readable economic and
    commuter impact metrics using the OD matrix and wage data.
    """
    G = GraphStore.get_healed() or GraphStore.get_osm_fallback()
    if G is None:
        raise HTTPException(status_code=404, detail="No graph available.")

    # The economic figures are a chain of fixed coefficients applied to one
    # node's normalised betweenness. Without a measured OD matrix they describe
    # no real commuter population, so no number is returned.
    prov = measured("od_matrix_csv")
    prov.inputs.append(graph_input(G))
    prov.require_available("/simulate/traffic-impact")

    node_map = {str(n): n for n in G.nodes()}
    ablated = [node_map[nid] for nid in req.ablated_node_ids if nid in node_map]

    result = compute_traffic_impact(G, ablated)
    for a_ in result.get("model_assumptions", []):
        prov.assume(a_)
    return JSONResponse(with_provenance(result, prov))


# ── Temporal Degradation ──────────────────────────────────────────────────────

class DegradationRequest(BaseModel):
    years: int = 10
    monte_carlo_runs: int = 50
    budget_scenario: str = "baseline"  # "optimistic", "baseline", or "austerity"

@router.post("/degradation-forecast")
def get_degradation_forecast(req: DegradationRequest):
    """
    Runs a Monte Carlo simulation to project network health decay
    over the next N years under different budget scenarios.
    """
    G = GraphStore.get_healed() or GraphStore.get_osm_fallback()
    if G is None:
        raise HTTPException(status_code=404, detail="No graph available.")

    if req.budget_scenario not in ("optimistic", "baseline", "austerity"):
        raise HTTPException(status_code=400, detail="budget_scenario must be optimistic, baseline, or austerity.")

    # Without road_conditions.csv the module returns a hardcoded linear decay
    # (0.72 - 0.03/yr) that is IDENTICAL for every budget scenario, making the
    # optimistic/baseline/austerity selector inert. That is not a forecast.
    prov = measured("road_conditions_csv")
    prov.inputs.append(graph_input(G))
    prov.require_available("/simulate/degradation-forecast")

    result = run_degradation_forecast(
        G,
        years=min(req.years, 20),
        monte_carlo_runs=min(req.monte_carlo_runs, 200),
        budget_scenario=req.budget_scenario,
    )
    prov.assume("per-segment health decays by its own degradation_rate_per_year "
                "with a Gaussian shock (sigma=0.015) and log-scaled maintenance offset")
    prov.assume(f"budget multiplier for '{req.budget_scenario}' applied to the "
                f"annual maintenance budget column")
    return JSONResponse(with_provenance(result, prov))


# ── Evacuation Planning ───────────────────────────────────────────────────────

class EvacuationRequest(BaseModel):
    ablated_node_ids: List[str] = []
    time_horizon_hours: int = 6


@router.post("/evacuate")
def run_evacuation(req: EvacuationRequest):
    """
    Plan multi-source evacuation routes from population zones to designated shelters.
    Implements NDMA/Sendai Framework Priority 4 evacuation protocol.

    Returns optimal zone-to-shelter assignments, ETAs, bottleneck edges,
    and shelter utilization. Respects ablated nodes (disaster-damaged roads).
    """
    from app.simulation.evacuation import plan_evacuation

    G = GraphStore.get_healed() or GraphStore.get_osm_fallback()
    if G is None:
        raise HTTPException(status_code=503, detail="Graph not loaded. Run /graph/build first.")

    # Resolve node IDs
    node_map = {str(n): n for n in G.nodes()}
    ablated = [node_map[nid] for nid in req.ablated_node_ids if nid in node_map]

    # app/simulation/evacuation.py is a stub returning empty assignments. An
    # empty plan is indistinguishable from "nobody needs evacuating", so the
    # endpoint declares itself unimplemented instead of returning it.
    raise HTTPException(
        status_code=503,
        detail={
            "error": "not_implemented",
            "endpoint": "/simulate/evacuate",
            "message": (
                "Multi-source evacuation planning is not implemented. "
                "app/simulation/evacuation.py returns a fixed empty result; "
                "returning it would imply a computed plan."
            ),
            "requires": ["shelter capacity layer", "population-to-node assignment"],
        },
    )
