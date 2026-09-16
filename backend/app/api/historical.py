"""
/simulate/historical — Historical disaster scenario endpoints.

Returns clearly separated:
  - OBSERVED: documented historical facts (IMD, BBMP, news)
  - MODEL_INPUTS: what parameters were fed into the simulation
  - SIMULATED: what Route Resilience algorithms actually computed
  - COMPARISON: directional agreement check (NOT validation)

No results are adjusted to match historical reports.
"""
import logging
from typing import Optional

import networkx as nx
from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import JSONResponse

from app.graph_pipeline.graph_build import GraphStore
from app.simulation.bengaluru_2022_demo import get_scenario, list_scenarios
from app.simulation.topography import flood_ablate, get_elevation_bounds
from app.data.population import query_population_nodes
from app.data.backtest import rainfall_to_water_level
from app.api.accessibility import _snap_to_graph, _get_affected_wards

logger = logging.getLogger(__name__)
router = APIRouter()


@router.get("/")
def list_historical_scenarios():
    """List all available historical disaster scenarios."""
    return JSONResponse({"scenarios": list_scenarios()})


@router.get("/{scenario_id}")
async def run_historical_scenario(
    scenario_id: str,
    override_water_level_m: Optional[float] = Query(
        default=None,
        description=(
            "Optional override water level (m ASL). If provided, overrides the scenario's "
            "default FITTED level (see bengaluru_2022_demo: the level is fitted to the "
            "documented extent, so agreement is circular and is NOT validation). "
            "Useful for sensitivity analysis only. "
            "Must be between DEM min and max."
        ),
    ),
):
    """
    Run a historical disaster scenario through the Route Resilience simulation pipeline.

    Returns a structured response with OBSERVED facts, MODEL INPUTS, and SIMULATED results
    clearly separated. Results are NOT adjusted to match historical reports.
    """
    scenario = get_scenario(scenario_id)
    if not scenario:
        raise HTTPException(
            status_code=404,
            detail=f"Scenario '{scenario_id}' not found. Use GET /simulate/historical/ to list available scenarios.",
        )

    G = GraphStore.get_healed() or GraphStore.get_osm_fallback()
    if G is None:
        raise HTTPException(status_code=503, detail="No road graph available. Backend may still be loading.")

    # ── Elevation bounds ───────────────────────────────────────────────────────
    bounds = get_elevation_bounds(G)

    # ── Rainfall runoff model result (for transparency — shows its limitation) ─
    observed_rainfall_mm = scenario["observed"]["rainfall_mm"]
    runoff_result = rainfall_to_water_level(observed_rainfall_mm)
    runoff_water_level_m = runoff_result["water_level_m"]
    flooded_at_runoff_level = flood_ablate(G, runoff_water_level_m)

    # ── Scenario water level ───────────────────────────────────────────────────
    # Use override if provided (for sensitivity analysis), else use scenario default
    if override_water_level_m is not None:
        if not (bounds["min"] <= override_water_level_m <= bounds["max"]):
            raise HTTPException(
                status_code=400,
                detail=(
                    f"override_water_level_m={override_water_level_m} is outside DEM range "
                    f"[{bounds['min']}, {bounds['max']}]."
                ),
            )
        scenario_water_level_m = override_water_level_m
        water_level_basis = f"user_override_{override_water_level_m}m"
        water_level_note = (
            f"User-supplied water level of {override_water_level_m}m "
            f"(overrides scenario default of {scenario['scenario_water_level_m']}m). "
            "Use for sensitivity analysis only."
        )
    else:
        scenario_water_level_m = scenario["scenario_water_level_m"]
        water_level_basis = scenario["scenario_water_level_basis"]
        water_level_note = scenario["scenario_water_level_derivation"]["step_2_calibrated_level"]["basis"]
    water_level_is_fitted = True   # M10: never present this as validation

    # ── Run flood simulation ───────────────────────────────────────────────────
    flooded = flood_ablate(G, scenario_water_level_m)
    flooded_set = set(flooded)
    total_nodes = G.number_of_nodes()

    # ── Road length affected ───────────────────────────────────────────────────
    road_length_m = sum(
        d.get("length", 0)
        for u, v, d in G.edges(data=True)
        if u in flooded_set or v in flooded_set
    )

    # ── WorldPop population ────────────────────────────────────────────────────
    pop_result = query_population_nodes(G, flooded)

    # ── Facility impact ────────────────────────────────────────────────────────
    from app.integrations.overpass import fetch_facilities
    s_bb, w_bb, n_bb, e_bb = 12.92, 77.57, 12.99, 77.64
    try:
        hospitals_raw = await fetch_facilities(
            s_bb, w_bb, n_bb, e_bb,
            amenities=["hospital", "clinic", "health_post"]
        )
        emergency_raw = await fetch_facilities(
            s_bb, w_bb, n_bb, e_bb,
            amenities=["fire_station", "police", "ambulance_station"]
        )
        hosp_nodes = _snap_to_graph(G, hospitals_raw)
        emerg_nodes = _snap_to_graph(G, emergency_raw)
        hospitals_in_flood_zone = sum(1 for n in hosp_nodes if n in flooded_set)
        emergency_in_flood_zone = sum(1 for n in emerg_nodes if n in flooded_set)
        hospitals_total = len(hosp_nodes)
        emergency_total = len(emerg_nodes)
    except Exception as exc:
        logger.warning(f"Facility lookup failed: {exc}. Reporting as unavailable.")
        hospitals_in_flood_zone = None
        emergency_in_flood_zone = None
        hospitals_total = None
        emergency_total = None

    # ── Ward breakdown ─────────────────────────────────────────────────────────
    ward_counts = _get_affected_wards(G, flooded)
    flooded_wards = {w: cnt for w, cnt in ward_counts.items() if w != "Outside Ward Boundary"}

    # ── Connectivity of degraded network ──────────────────────────────────────
    surviving_nodes = [n for n in G.nodes() if n not in flooded_set]
    if surviving_nodes:
        G_surviving = G.subgraph(surviving_nodes)
        surviving_components = nx.number_connected_components(G_surviving)
        surviving_lcc_size = len(max(nx.connected_components(G_surviving), key=len))
    else:
        surviving_components = 0
        surviving_lcc_size = 0

    # ── Directional comparison ─────────────────────────────────────────────────
    known_areas = set(scenario["observed"]["known_affected_areas_qualitative"])
    model_wards = set(flooded_wards.keys())
    # Fuzzy match: check if any known area name appears as a substring of a ward name or vice versa
    overlap_exact = known_areas & model_wards
    overlap_partial = set()
    for known in known_areas:
        for ward in model_wards:
            if known.lower() in ward.lower() or ward.lower() in known.lower():
                overlap_partial.add(known)
    overlap_partial -= overlap_exact

    # ── Build response ─────────────────────────────────────────────────────────
    result = {
        # ── Scenario identification ────────────────────────────────────────────
        "scenario_metadata": {
            "id": scenario["id"],
            "name": scenario["name"],
            "peak_date": scenario["peak_date"],
            "data_type": scenario["data_type"],
            "description": scenario["description"],
        },

        # ── OBSERVED HISTORICAL FACTS ──────────────────────────────────────────
        "observed_historical_facts": {
            "_section": "OBSERVED",
            "_label": (
                "Documented from IMD, BBMP, and news archives. "
                "NOT computed by Route Resilience algorithms."
            ),
            "rainfall_mm": observed_rainfall_mm,
            "rainfall_source": scenario["observed"]["rainfall_source"],
            "rainfall_precision": scenario["observed"]["rainfall_precision"],
            "rainfall_source_note": scenario["observed"]["rainfall_source_note"],
            "known_affected_areas_qualitative": scenario["observed"]["known_affected_areas_qualitative"],
            "known_affected_areas_source": scenario["observed"]["known_affected_areas_source"],
            "known_affected_areas_note": scenario["observed"]["known_affected_areas_note"],
            "infrastructure_impact_note": scenario["observed"]["infrastructure_impact_note"],
        },

        # ── MODEL INPUTS ───────────────────────────────────────────────────────
        "model_inputs": {
            "_section": "MODEL_INPUTS",
            "_label": "Parameters fed into Route Resilience simulation algorithms.",
            "dem_source": "SRTMGL1_30m",
            "graph_source": "OpenStreetMap_via_OSMnx_2023",
            "flood_model": "static_DEM_height_threshold_inundation",
            "population_source": "WorldPop_2020_UNadj_constrained_100m",
            "graph_nodes": total_nodes,
            "graph_edges": G.number_of_edges(),
            "dem_elevation_range": {
                "min_m": bounds["min"],
                "max_m": bounds["max"],
                "mean_m": bounds["mean"],
                "unknown_nodes": bounds["unknown_count"],
            },
            "rainfall_runoff_model_output": {
                "_note": (
                    "Shown for transparency. Reveals model limitation for extreme events. "
                    "This water level is NOT used as the scenario input — see scenario_water_level."
                ),
                "rainfall_mm": observed_rainfall_mm,
                **runoff_result,
                "flooded_nodes_at_this_level": len(flooded_at_runoff_level),
                "limitation": scenario["scenario_water_level_derivation"]["step_1_rainfall_runoff"]["model_limitation"],
            },
            "scenario_water_level_m": scenario_water_level_m,
            "scenario_water_level_basis": water_level_basis,
            "scenario_water_level_note": water_level_note,
        },

        # ── SIMULATED RESULTS ──────────────────────────────────────────────────
        "simulated_results": {
            "_section": "SIMULATED",
            "_label": (
                "Computed by Route Resilience algorithms. "
                "NOT validated against official flood maps or satellite imagery."
            ),
            "water_level_m": scenario_water_level_m,
            "flood_model": "static_DEM_height_threshold_inundation",
            "flooded_nodes": len(flooded),
            "total_nodes": total_nodes,
            "flood_fraction_pct": round(len(flooded) / total_nodes * 100, 2) if total_nodes else 0,
            "road_length_flooded_km": round(road_length_m / 1000, 2),
            "surviving_network": {
                "surviving_nodes": total_nodes - len(flooded),
                "surviving_components": surviving_components,
                "largest_connected_component_nodes": surviving_lcc_size,
            },
            "population_in_flood_zone": {
                "value": pop_result.get("population", 0),
                "source": pop_result.get("source", "unknown"),
                "methodology": pop_result.get("estimation_method", "unknown"),
                "note": pop_result.get("note", "Not census-verified."),
            },
            "facility_impact": {
                "hospitals_in_flood_zone": hospitals_in_flood_zone,
                "hospitals_total_in_aoi": hospitals_total,
                "emergency_stations_in_flood_zone": emergency_in_flood_zone,
                "emergency_total_in_aoi": emergency_total,
                "source": "OpenStreetMap_via_Overpass_API",
                "note": (
                    "OSM facilities snapped to nearest road graph node. "
                    "Counts nodes within flood zone — not a validated facility database."
                ),
            },
            "ward_impact": {
                "wards_with_flooded_nodes": len(flooded_wards),
                "top_affected_wards": sorted(
                    flooded_wards.items(), key=lambda x: x[1], reverse=True
                )[:15],
                "ward_boundary_source": "BBMP_GeoJSON",
                "population_source": "BBMP_GeoJSON_TOT_P_field_2011_census",
            },
        },

        # ── DIRECTIONAL COMPARISON ─────────────────────────────────────────────
        "directional_comparison": {
            "_section": "COMPARISON",
            "_label": (
                "Model-predicted affected wards vs. qualitatively documented areas. "
                "NOT a precision/recall validation. Reference set is news-reported, not surveyed."
            ),
            "model_predicted_wards_count": len(flooded_wards),
            "documented_affected_areas_count": len(known_areas),
            "exact_name_overlap": sorted(overlap_exact),
            "partial_name_overlap": sorted(overlap_partial),
            "areas_outside_aoi": [
                "Bellandur (lon ≈77.67 — outside AOI east boundary lon 77.64)",
                "Marathahalli (lon ≈77.70 — outside AOI)",
                "Whitefield (lon ≈77.75 — outside AOI)",
                "Sarjapur Road corridor (partially outside AOI)",
            ],
            "aoi_coverage_note": scenario["aoi_coverage_note"],
            "comparison_note": (
                "Several documented areas (Bellandur, Marathahalli) are outside the current "
                "AOI and cannot be evaluated. Of in-AOI areas, partial name matches indicate "
                "the model identifies nearby ward-level areas. This is a directional agreement "
                "check only — not a recall/precision metric."
            ),
        },

        # ── MODEL LIMITATIONS ──────────────────────────────────────────────────
        "model_limitations": scenario["model_limitations"],
    }

    # Store in GraphStore for Copilot context
    GraphStore.set_last_flood_result({
        "scenario": scenario["name"],
        "scenario_id": scenario["id"],
        "water_level": scenario_water_level_m,
        "flooded_nodes_count": len(flooded),
        "road_length_flooded_km": round(road_length_m / 1000, 2),
        "population_in_flood_zone": pop_result.get("population", 0),
        "hospitals_in_flood_zone": hospitals_in_flood_zone,
        "wards_affected": len(flooded_wards),
        "observed_rainfall_mm": observed_rainfall_mm,
        "data_type": "HISTORICAL_SCENARIO",
    })

    logger.info(
        f"Historical scenario '{scenario_id}' complete: "
        f"{len(flooded)} nodes flooded at {scenario_water_level_m}m, "
        f"{len(flooded_wards)} wards affected, "
        f"pop={pop_result.get('population', 0):,}"
    )

    return JSONResponse(result)
