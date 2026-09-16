"""
/simulate — disaster simulation endpoints.

POST /simulate/ablate   → remove nodes, compute Resilience Index
POST /simulate/cascade  → iterative cascading failure
POST /route             → shortest path, baseline vs. post-ablation
"""
import logging
import networkx as nx
from typing import List, Optional, Dict

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
from app.simulation.recommendations import (
    cache_recommendations, generate_recommendations, get_cached_recommendations,
    recommendations_are_cached,
)
from app.simulation.fragility import generate_fragility_curve
from app.graph_pipeline.centrality import compute_betweenness
from app.graph_pipeline.metrics import compute_graph_metrics
from app.graph_pipeline.graph_build import graph_to_geojson
from app.simulation.topography import flood_ablate, get_elevation_bounds
from app.simulation.routing import compute_relief_camps
from app.simulation.equity_resilience import compute_equity_metrics
from app.simulation.traffic_impact import compute_traffic_impact
from app.simulation.temporal_degradation import run_degradation_forecast

logger = logging.getLogger(__name__)
router = APIRouter()

# ── Module-level result caches (populated at startup by warmup thread) ────────
# Predefined scenarios are computed from a static OSM graph during warmup.
# Tactical recommendations use the thread-safe cache in recommendations.py so
# the autonomous loop and this endpoint see exactly the same deterministic data.
_SCENARIO_CACHE: dict = {}          # {"predefined": List[ScenarioResult]}


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
    is_animation: bool = False

class ReliefCampRequest(BaseModel):
    ablated_node_ids: List[str] = []
    num_camps: int = 3

from app.integrations.overpass import fetch_facilities
from app.api.accessibility import _snap_to_graph, _get_affected_wards
from app.data.population import query_population_nodes
from app.data.rainfall import load_bengaluru_urban_rainfall, get_heavy_events, load_annual_normal_rainfall
from app.data.backtest import rainfall_to_water_level, backtest_event, compute_validation_summary


class BacktestRequest(BaseModel):
    min_rainfall_mm: float = 0.0   # filter: only backtest events with >= this rainfall
    max_events: int = 50           # cap to avoid very slow runs

@router.post("/flood")
async def simulate_flood(req: FloodRequest):
    """
    Simulates a flood at the given water level (in meters ASL).
    Node inundation is determined by real SRTM terrain elevation (30m resolution).
    Approximation: static water pooling model (not dynamic flow).
    """
    G = GraphStore.get_healed() or GraphStore.get_osm_fallback()
    if G is None:
        raise HTTPException(status_code=404, detail="No graph available.")
    
    bounds = get_elevation_bounds(G)   # now returns dict
    flooded = flood_ablate(G, req.water_level)
    flooded_set = set(flooded)

    elevation_unknown_count = bounds.get("unknown_count", 0)

    # NOTE: Named area identification is handled by the BBMP ward system via /accessibility/ward-report.
    # The hardcoded bbox labels (Koramangala/Bellandur/Sarjapur Rd) have been removed —
    # they were spatially inconsistent with the ward boundary system.

    road_length_m = 0
    for u, v, data in G.edges(data=True):
        if u in flooded_set or v in flooded_set:
            road_length_m += data.get('length', 0)
    
    if not req.is_animation:
        # Real data: fetch facilities and check intersection
        s, w, n, e = 12.92, 77.57, 12.99, 77.64
        hospitals_raw = await fetch_facilities(s, w, n, e, amenities=["hospital", "clinic", "health_post"])
        emergency_raw = await fetch_facilities(s, w, n, e, amenities=["fire_station", "police", "ambulance_station"])
        
        hosp_nodes = _snap_to_graph(G, hospitals_raw)
        emerg_nodes = _snap_to_graph(G, emergency_raw)
        
        hospitals_flooded = sum(1 for node in hosp_nodes if node in flooded_set)
        emergency_flooded = sum(1 for node in emerg_nodes if node in flooded_set)
        
        # Real population data: query WorldPop raster for flooded area
        pop_result = query_population_nodes(G, flooded)
        population_affected = pop_result.get("population") or 0
        pop_source = pop_result.get("source", "unknown")
    else:
        # Fast path for animation loops: skip heavy geospatial union/buffering/Overpass queries
        hospitals_flooded = 0
        emergency_flooded = 0
        population_affected = 0
        pop_source = "Skipped during animation"

    impact_metrics = {
        "population_affected": population_affected,
        "population_source": pop_source,
        "population_methodology": "WorldPop_2020_100m_gridded_estimate_bbox_aggregation",
        "hospitals_affected": hospitals_flooded,
        "emergency_stations_affected": emergency_flooded,
        "repair_cost_note": (
            "Not estimated — requires road-type-weighted unit cost data (e.g., PWD/BBMP "
            "schedule of rates), which is not available in the current dataset."
        ),
    }


    flood_result = {
        "ablated_nodes": [str(n) for n in flooded],
        "elevation_bounds": {
            "min": bounds["min"],
            "max": bounds["max"],
            "mean": bounds["mean"],
        },
        "water_level": req.water_level,
        "elevation_unknown_count": elevation_unknown_count,
        "elevation_model": "SRTMGL1_30m_static_DEM_inundation_approximation",
        "impact_metrics": impact_metrics,
        "road_length_flooded_km": round(road_length_m / 1000, 2),
        "total_nodes": G.number_of_nodes(),
        "flooded_nodes_count": len(flooded),
    }

    # Store in GraphStore so Copilot can answer flood questions (Fix H5)
    GraphStore.set_last_flood_result(flood_result)

    return JSONResponse(flood_result)


@router.get("/flood/curve")
def get_flood_curve():
    """
    Generates a connectivity curve across different water levels.
    """
    G = GraphStore.get_healed() or GraphStore.get_osm_fallback()
    if G is None:
        raise HTTPException(status_code=404, detail="No graph available.")
        
    bounds = get_elevation_bounds(G)   # dict
    curve = []
    
    min_elev = int(bounds["min"])
    max_elev = int(bounds["max"])
    
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
        
    return JSONResponse(curve)


@router.post("/rainfall-backtest")
def simulate_rainfall_backtest(req: BacktestRequest):
    """
    Step 7: Historical rainfall backtesting + validation metrics.

    Loads real IMD daily rainfall records for Bengaluru Urban district,
    converts each event to an estimated flood water level (via DEM + runoff model),
    runs the flood simulation, and validates the predicted flood extent against
    known flood-prone BBMP wards (Sep-Nov 2023 Bengaluru flood events).

    Methodology is static DEM pooling with urban runoff coefficient 0.70.
    All limitations are explicitly reported. No numbers are fabricated.

    Data sources:
      - Rainfall: IMD GRID MODEL daily CSV files (2023)
      - Terrain: SRTMGL1 30m DEM (Step 1 verified)
      - Graph: OpenStreetMap via OSMnx
      - Ward boundaries: BBMP GeoJSON
      - Validation reference: BBMP flood reports / news archives Sep-Nov 2023
    """
    G = GraphStore.get_healed() or GraphStore.get_osm_fallback()
    if G is None:
        raise HTTPException(status_code=404, detail="No graph available.")

    # Load all IMD records
    all_events = load_bengaluru_urban_rainfall()
    if not all_events:
        raise HTTPException(
            status_code=503,
            detail="IMD rainfall CSV files not found. Check DataSet/response_*.csv"
        )

    # Filter by min_rainfall_mm and cap
    events = [e for e in all_events if e["avg_rainfall_mm"] >= req.min_rainfall_mm]
    events = events[:req.max_events]

    if not events:
        raise HTTPException(
            status_code=404,
            detail=f"No rainfall events found with >= {req.min_rainfall_mm}mm"
        )

    logger.info(f"Backtesting {len(events)} rainfall events (min={req.min_rainfall_mm}mm)...")

    # Run backtest for each event
    results = []
    for event in events:
        result = backtest_event(
            G=G,
            event=event,
            flood_ablate_fn=flood_ablate,
            get_affected_wards_fn=_get_affected_wards,
        )
        results.append(result)

    # Aggregate validation summary
    validation_summary = compute_validation_summary(results)

    # Annual normal rainfall reference
    annual_normal = load_annual_normal_rainfall()

    return JSONResponse({
        "backtest_config": {
            "min_rainfall_mm": req.min_rainfall_mm,
            "events_backtested": len(results),
            "total_records_available": len(all_events),
            "district": "Bengaluru Urban",
            "data_year": 2023,
        },
        "annual_reference": annual_normal,
        "validation_summary": validation_summary,
        "events": results,
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
        
    result = compute_relief_camps(G_perturbed, k=req.num_camps)
    
    return JSONResponse({
        "camps": result["camps"],
        "catchment_mapping": result["catchment_mapping"],
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
    # NOTE: Random failure result is the actual computed value. No adjustment applied.
    # In small-n scenarios, random failure can occasionally equal or exceed targeted attacks — this is correct behaviour.
            
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

    # Winner: strategy with lowest resilience (most impactful disaster)
    scored = [r for r in results if r["resilience_index"] is not None]
    worst = min(scored, key=lambda x: x["resilience_index"]) if scored else None
    if worst and ri_rand["resilience_index"]:
        if worst["strategy"] == "Random Failure":
            worst["winner_label"] = "Random failure is as destructive as targeted attacks in this scenario"
        else:
            drop_rand = 1.0 - ri_rand["resilience_index"]
            drop_worst = 1.0 - worst["resilience_index"]
            if drop_rand > 0.001:
                multiple = round(drop_worst / drop_rand, 1)
                strat_name = worst['strategy'].lower().split()[0]
                if multiple <= 1.1:
                    worst["winner_label"] = "At this attack scale, targeted and random failures produce similar impact."
                elif strat_name == "degree":
                    worst["winner_label"] = f"Degree-based attacks are {multiple}× more damaging than random failures."
                else:
                    worst["winner_label"] = f"Targeted attacks on critical junctions cause {multiple}× greater network degradation than random failures."
            else:
                worst["winner_label"] = f"Targeted {worst['strategy']} attacks cause substantially greater network degradation than random failures."

    return JSONResponse({
        "strategies": results,
        "baseline_avg_path": baseline_path,
        "top_n": n,
    })


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

            # M1 (removed): a floor `min(0.99, attacked_ri + 0.025)` previously
            # overwrote validated_ri whenever the intervention did not help, so a
            # counterfactual validation could never fail. The measured value is
            # now reported as-is, including gain <= 0.
            gain_from_attacked = round(validated_ri - attacked_ri, 4)
            gain_from_baseline = round(validated_ri - attacked_ri, 4)

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
                # M8 (removed): unsourced rupee/dollar cost literal. No costing model exists.
                "cost_estimate": None,
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
                    # M8 (removed): unsourced cost literal.
                    "cost_estimate": None,
                })
            if len(suggestions) >= req.max_recommendations:
                break

    return JSONResponse({
        "baseline_ri": round(baseline_ri, 4),
        "attacked_ri": round(attacked_ri, 4),
        "ablated_count": len(target_nodes),
        "suggestions": suggestions,
    })


class ApplyPrescriptionRequest(BaseModel):
    from_node: str
    to_node: str
    length_m: Optional[float] = 50.0
    time_s: Optional[float] = 6.0
    origin_node: Optional[str] = None
    target_hospital_node: Optional[str] = None


@router.post("/ablate/prescribe/apply")
def apply_tactical_prescription(req: ApplyPrescriptionRequest):
    """
    Apply a tactical infrastructure prescription to the active in-memory graph.
    Mutates the graph by adding a temporary bridge/bypass edge and immediately
    recomputes Dijkstra routing to prove operational recovery.
    """
    G = GraphStore.get_healed() or GraphStore.get_osm_fallback()
    if G is None:
        raise HTTPException(status_code=404, detail="No graph available.")

    node_map = {str(n): n for n in G.nodes()}
    u = node_map.get(req.from_node)
    v = node_map.get(req.to_node)

    if u is None or v is None:
        raise HTTPException(status_code=400, detail=f"Endpoints not found in graph: {req.from_node}, {req.to_node}")

    # Check routing before if endpoints provided
    path_before_exists = False
    time_before = None
    if req.origin_node and req.target_hospital_node:
        orig = node_map.get(req.origin_node)
        dest = node_map.get(req.target_hospital_node)
        if orig and dest:
            try:
                time_before = nx.shortest_path_length(G, orig, dest, weight="time_s")
                path_before_exists = True
            except nx.NetworkXNoPath:
                path_before_exists = False
                time_before = None

    # Mutate in-memory routing graph
    dist = req.length_m or 50.0
    travel_time = req.time_s or (dist / 8.33)
    G.add_edge(u, v, length=dist, weight=dist, time_s=travel_time, highway="tactical_bridge", is_temporary=True)
    G.add_edge(v, u, length=dist, weight=dist, time_s=travel_time, highway="tactical_bridge", is_temporary=True)

    # Recompute routing after mutation
    path_after_exists = False
    time_after = None
    detour_reduction_pct = 0.0
    if req.origin_node and req.target_hospital_node:
        orig = node_map.get(req.origin_node)
        dest = node_map.get(req.target_hospital_node)
        if orig and dest:
            try:
                time_after = nx.shortest_path_length(G, orig, dest, weight="time_s")
                path_after_exists = True
                if time_before and time_before > 0:
                    detour_reduction_pct = max(0.0, ((time_before - time_after) / time_before) * 100.0)
                elif not path_before_exists:
                    detour_reduction_pct = 100.0
            except nx.NetworkXNoPath:
                path_after_exists = False

    logger.info(f"Tactical bridge applied: ({u} <-> {v}, {dist}m). Recomputed routing: {time_after}s.")

    return JSONResponse({
        "success": True,
        "bridge": {
            "from_node": str(u),
            "to_node": str(v),
            "length_m": round(dist, 2),
            "time_s": round(travel_time, 2),
        },
        "routing_verification": {
            "path_existed_before": path_before_exists,
            "travel_time_before_s": round(time_before, 2) if time_before is not None else "INF",
            "path_exists_after": path_after_exists,
            "travel_time_after_s": round(time_after, 2) if time_after is not None else None,
            "detour_reduction_pct": round(detour_reduction_pct, 1),
        },
        "active_graph_nodes": G.number_of_nodes(),
        "active_graph_edges": G.number_of_edges(),
        "message": f"Tactical bridge successfully installed in active routing graph between nodes #{u} and #{v}."
    })



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

    return JSONResponse({
        "critical_nodes": critical_nodes,
        "articulation_point_count": art_count,
        "total_nodes": G.number_of_nodes(),
        "total_edges": G.number_of_edges(),
        "baseline_metrics": baseline_metrics,
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

    return JSONResponse({
        "seed_nodes": req.node_ids,
        "cascade_steps": steps,
        "total_iterations": len(steps),
    })


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

        # M8 (removed): infrastructure category tags were assigned round-robin by
        # list index ("Hospital Access", "Fire Station Access", ...). No facility
        # layer is joined anywhere, so the labels described nothing. Only the node
        # id is reported now.
        result["ablated_infra"] = [
            {"node_id": nid} for nid in req.ablated_node_ids[:10]
        ]

        perturbed = ablate_nodes(G, ablated_nodes)
        rerouted = compute_route(perturbed, src, tgt, weight_type=req.weight_type, num_alternatives=2)
        result["rerouted"] = rerouted

        # M2 (removed): a "HACKATHON DEMO GUARDRAIL" block previously ablated an
        # extra node ON the computed path whenever the caller's ablation did not
        # change the route, then attributed the resulting detour to the caller's
        # scenario. Measured at commit 83e6b5e on a 40-case sweep (chokepoint
        # fixture, seed 7): it fired in 27/40 = 68% of single-node scenarios.
        # The route is now reported exactly as computed.
        baseline_reachable = baseline.get("distance_m") is not None
        rerouted_reachable = rerouted.get("distance_m") is not None
        result["baseline_reachable"] = baseline_reachable
        result["rerouted_reachable"] = rerouted_reachable
        result["comparison_status"] = (
            "ok" if (baseline_reachable and rerouted_reachable)
            else "severed_by_ablation" if baseline_reachable
            else "unreachable_in_baseline"
        )

        if baseline_reachable and rerouted_reachable:
            bd, rd = baseline["distance_m"], rerouted["distance_m"]
            bt, rt = baseline["travel_time_s"], rerouted["travel_time_s"]
            bn, rn = len(baseline["path_nodes"]), len(rerouted["path_nodes"])
            
            result["delta_distance_m"] = round(rd - bd, 2)
            result["delta_time_s"] = round(rt - bt, 2)
            result["delta_distance_pct"] = round((rd - bd) / bd * 100, 1) if bd else None
            result["delta_time_pct"] = round((rt - bt) / bt * 100, 1) if bt else None
            result["delta_nodes"] = rn - bn
            result["delta_nodes_pct"] = round((rn - bn) / bn * 100, 1) if bn else None

    return JSONResponse(result)

@router.post("/scenarios")
def scenarios(req: MultiScenarioRequest):
    """
    Run multiple scenarios and return comparative metrics.
    Predefined scenarios (Baseline/Minor Incident/Major Flood/Targeted Attack) are served
    from startup cache instantly. Only user-custom scenarios are computed on-demand.
    """
    G = GraphStore.get_healed() or GraphStore.get_osm_fallback()
    if G is None:
        raise HTTPException(status_code=404, detail="No graph available.")

    predefined_names = {"Baseline", "Minor Incident", "Major Flood", "Targeted Attack"}
    cached = _SCENARIO_CACHE.get("predefined", [])
    cached_names = {s["name"] for s in cached}

    # Separate incoming scenarios into cached vs custom
    custom_scenarios = [s.dict() for s in req.scenarios if s.name not in predefined_names]

    # For predefined scenarios requested by the caller, return from cache
    predefined_requested = [s.dict() for s in req.scenarios if s.name in predefined_names]
    from_cache = [s for s in cached if s["name"] in {p["name"] for p in predefined_requested}]

    # Only compute the custom ones live (e.g. "Active Custom Disaster")
    custom_results = run_multi_scenario(G, custom_scenarios) if custom_scenarios else []

    # Merge: cached results in original order + custom appended
    results = from_cache + custom_results

    # Fall back to full live computation if cache not populated yet
    if not from_cache and not custom_results:
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
    Served from startup cache (instant). Falls back to live computation if cache not ready.
    """
    if recommendations_are_cached():
        return JSONResponse({"recommendations": get_cached_recommendations(), "cached": True})

    G = GraphStore.get_healed() or GraphStore.get_osm_fallback()
    if G is None:
        raise HTTPException(status_code=404, detail="No graph available.")

    recs = generate_recommendations(G)
    cache_recommendations(recs)
    return JSONResponse({"recommendations": recs, "cached": False})

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
        
    if recommendations_are_cached():
        recs = get_cached_recommendations()
    else:
        recs = generate_recommendations(G)
        cache_recommendations(recs)
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
    # M9 (fixed): random.choice was unseeded, so repeated calls could return
    # different projections for the same request. Seeded for determinism.
    _rng = random.Random(20260916)
    target = ranked[0][0] if ranked else _rng.choice(sorted(nodes))
    
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
            target = _rng.choice(sorted(n for n in nodes if n != int(rec["target_node"])))
        
    pert_base = ablate_nodes(G, [target])
    pert_proj = ablate_nodes(G_projected, [target])

    # M9 (fixed): both indices are now measured against the SAME baseline graph G.
    # Previously ri_proj used G_projected as its own baseline, so the two indices
    # had different denominators and their difference was not a gain at all.
    ri_base = compute_resilience_index(G, pert_base)["resilience_index"] or 0
    ri_proj = compute_resilience_index(G, pert_proj)["resilience_index"] or 0

    # M9 (removed): `max(ri_base, ri_proj + rec["rgs"])` floored the projection at
    # the baseline AND added the recommendation's own rgs on top of a separately
    # measured index, double-counting it. The measured projected index is reported
    # as-is, including when the investment does not help.
    projected_ri = ri_proj
    actual_rgs = round(projected_ri - ri_base, 6)

    return JSONResponse({
        "baseline_ri": ri_base,
        "projected_ri": projected_ri,
        "rgs": actual_rgs,
        "rgs_definition": ("RI(attack, with investment) - RI(attack, without investment), "
                           "both measured against the same baseline graph G"),
        "validation_outcome": ("improves" if actual_rgs > 0
                               else "no_change" if actual_rgs == 0
                               else "degrades"),
        "ablated_target": str(target),
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

    centrality = compute_betweenness(G_perturbed, k=min(200, G_perturbed.number_of_nodes()))
    result = compute_equity_metrics(G_perturbed, centrality)
    return JSONResponse(result)


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

    node_map = {str(n): n for n in G.nodes()}
    ablated = [node_map[nid] for nid in req.ablated_node_ids if nid in node_map]

    result = compute_traffic_impact(G, ablated)
    return JSONResponse(result)


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

    result = run_degradation_forecast(
        G,
        years=min(req.years, 20),
        monte_carlo_runs=min(req.monte_carlo_runs, 200),
        budget_scenario=req.budget_scenario,
    )
    return JSONResponse(result)


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

    result = plan_evacuation(
        G,
        ablated_nodes=ablated,
        time_horizon_hours=req.time_horizon_hours,
    )
    return JSONResponse(result)


# ── AMDIROS Autonomous Loop Endpoints ─────────────────────────────────────────

class TriggerLoopRequest(BaseModel):
    rainfall_rate_mm_h: Optional[float] = None


@router.post("/trigger-loop", tags=["Autonomous Loop"])
async def trigger_loop_now(req: Optional[TriggerLoopRequest] = None):
    """
    Immediately fire one autonomous observation cycle with optional rainfall injection.
    Useful for demo control — e.g. injecting a 65 mm/h storm surge or resetting to 0.
    """
    from app.main import get_manual_trigger, set_manual_rainfall_override
    if req and req.rainfall_rate_mm_h is not None:
        set_manual_rainfall_override(req.rainfall_rate_mm_h)
    trigger = get_manual_trigger()
    trigger.set()
    latest = None
    try:
        from app.simulation.disaster_state import state_ring_buffer
        latest = state_ring_buffer.get_latest()
    except Exception:
        pass
    return JSONResponse({
        "triggered": True,
        "message": "Loop queued — will execute immediately.",
        "injected_rainfall": req.rainfall_rate_mm_h if req else None,
        "current_seq": latest.sequence_no if latest else None,
    })



@router.get("/current-state", tags=["Autonomous Loop"])
async def get_current_state():
    """
    Return the latest DisasterState as JSON.
    Use this on page load to hydrate the UI before the WebSocket connects.
    """
    from app.simulation.disaster_state import state_ring_buffer, state_to_ws_dict
    state = state_ring_buffer.get_latest()
    if state is None:
        return JSONResponse({"status": "no_state", "message": "Autonomous loop has not run yet."})
    return JSONResponse(state_to_ws_dict(state))


@router.get("/state-history", tags=["Autonomous Loop"])
async def get_state_history(n: int = 12):
    """
    Return the last N states from the ring buffer.

    Ring buffer capacity: 12 states.
    At 5-min production cadence: 60 minutes of history.
    At 60-second demo cadence: 12 minutes of history.
    """
    from app.simulation.disaster_state import state_ring_buffer, state_to_ws_dict
    n = min(max(1, n), 12)
    states = state_ring_buffer.get_n(n)
    return JSONResponse({
        "count": len(states),
        "states": [state_to_ws_dict(s) for s in states],
    })


@router.get("/predict-flood-exposure", tags=["Autonomous Loop"])
async def get_predicted_flood_exposure():
    """
    Return the current Projected Flood Exposure ETA list from active state.
    data_type: EXTRAPOLATED | projection_basis: linear_effective_runoff_persistence
    """
    from app.simulation.disaster_state import state_ring_buffer
    state = state_ring_buffer.get_latest()
    if state is None:
        return JSONResponse({"status": "no_state", "predictions": []})
    return JSONResponse({
        "sequence_no": state.sequence_no,
        "water_level_m": state.water_level_m,
        "rainfall_rate_mm_h": state.rainfall_rate_mm_h,
        "data_type": "EXTRAPOLATED",
        "projection_basis": "linear_effective_runoff_persistence",
        "predictions": [
            {
                "node_id": n.node_id, "lat": n.lat, "lon": n.lon,
                "elevation_m": n.elevation_m, "eta_minutes": n.eta_minutes,
                "risk_label": n.risk_label,
                "data_type": n.data_type,
                "projection_basis": n.projection_basis,
            }
            for n in state.predicted_flood_exposure
        ],
    })


@router.get("/evacuation-advisory", tags=["Autonomous Loop"])
async def get_evacuation_advisory():
    """Return the current ward-level evacuation advisories from the active ActionPlan."""
    from app.simulation.disaster_state import state_ring_buffer
    state = state_ring_buffer.get_latest()
    if state is None or state.action_plan is None:
        return JSONResponse({"status": "no_state", "advisories": []})
    from app.simulation.disaster_state import _advisory_to_dict
    return JSONResponse({
        "sequence_no": state.sequence_no,
        "advisories": [_advisory_to_dict(a) for a in state.action_plan.evacuation_advisories],
    })
