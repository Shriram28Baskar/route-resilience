"""
/simulate — disaster simulation endpoints.

POST /simulate/ablate   → remove nodes, compute Resilience Index
POST /simulate/cascade  → iterative cascading failure
POST /route             → shortest path, baseline vs. post-ablation
"""
import logging
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
from app.simulation.topography import flood_ablate, get_elevation_bounds
from app.simulation.routing import compute_relief_camps

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
    
    bounds = get_elevation_bounds(G)
    flooded = flood_ablate(G, req.water_level)
    
    return JSONResponse({
        "ablated_nodes": [str(n) for n in flooded],
        "elevation_bounds": {"min": bounds[0], "max": bounds[1]},
        "water_level": req.water_level
    })

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
        
    camps = compute_relief_camps(G_perturbed, k=req.num_camps)
    
    return JSONResponse({
        "camps": camps
    })

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

    return JSONResponse({
        "ablated_nodes": node_ids,
        "graph_geojson": geojson,
        "baseline_metrics": baseline_metrics,
        "perturbed_metrics": perturbed_metrics,
        "resilience_index": ri["resilience_index"],
        "baseline_avg_path_length": ri["baseline_avg_path"],
        "perturbed_avg_path_length": ri["perturbed_avg_path"],
        "disconnected": ri["disconnected"],
        "population_impact": pop_impact,
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

    return JSONResponse({
        "seed_nodes": req.node_ids,
        "cascade_steps": steps,
        "total_iterations": len(steps),
    })


@router.post("/route")
def route(req: RouteRequest):
    """
    Return the shortest path between two nodes on the baseline graph and,
    optionally, on the post-ablation graph. Includes travel-time estimates.
    """
    G = GraphStore.get_healed() or GraphStore.get_osm_fallback()
    if G is None:
        raise HTTPException(status_code=404, detail="No graph available.")

    node_map = {str(n): n for n in G.nodes()}
    src = node_map.get(req.source_node)
    tgt = node_map.get(req.target_node)

    if src is None or tgt is None:
        raise HTTPException(status_code=400, detail="Source or target node not found.")

    baseline = compute_route(G, src, tgt, weight_type=req.weight_type)

    result = {"baseline": baseline, "rerouted": None, "delta_distance_m": None, "delta_time_s": None}

    if req.ablated_node_ids:
        ablated_nodes = [node_map[nid] for nid in req.ablated_node_ids if nid in node_map]
        perturbed = ablate_nodes(G, ablated_nodes)
        rerouted = compute_route(perturbed, src, tgt, weight_type=req.weight_type)
        result["rerouted"] = rerouted
        if baseline.get("distance_m") is not None and rerouted.get("distance_m") is not None:
            result["delta_distance_m"] = rerouted["distance_m"] - baseline["distance_m"]
            result["delta_time_s"] = rerouted["travel_time_s"] - baseline["travel_time_s"]

    return JSONResponse(result)

@router.post("/scenarios")
def scenarios(req: MultiScenarioRequest):
    """
    Run multiple scenarios and return comparative metrics.
    """
    G = GraphStore.get_healed() or GraphStore.get_osm_fallback()
    if G is None:
        raise HTTPException(status_code=404, detail="No graph available.")
        
    results = run_multi_scenario(G, [s.dict() for s in req.scenarios])
    return JSONResponse({"scenarios": results})



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
    
    return JSONResponse({
        "global_resilience_score": round(score, 4),
        "metrics": metrics
    })

@router.get("/fragility")
def get_fragility():
    """
    Computes and returns the fragility curve and percolation threshold.
    """
    G = GraphStore.get_healed() or GraphStore.get_osm_fallback()
    if G is None:
        raise HTTPException(status_code=404, detail="No graph available.")
        
    result = generate_fragility_curve(G, num_steps=20)
    return JSONResponse(result)

@router.get("/recommendations")
def get_recommendations():
    """
    Returns infrastructure upgrade and bypass recommendations based on resilience gain.
    """
    G = GraphStore.get_healed() or GraphStore.get_osm_fallback()
    if G is None:
        raise HTTPException(status_code=404, detail="No graph available.")

    recs = generate_recommendations(G)
    return JSONResponse({"recommendations": recs})

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
    
    return JSONResponse({
        "baseline_ri": ri_base,
        "projected_ri": max(ri_base, ri_proj + rec["rgs"]),
        "rgs": rec["rgs"],
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

    return JSONResponse({"timeline_steps": steps})
