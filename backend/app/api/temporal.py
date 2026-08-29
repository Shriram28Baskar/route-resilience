"""
/simulate/temporal-projection — NOW → +30min → +60min → +90min flood projection.

Data honesty contract:
  OBSERVED   : rain.1h from OWM /weather API (past-hour accumulation).
  EXTRAPOLATED: future horizons from linear rainfall-persistence model.
  MODELED    : inundation, road length, population, ward, connectivity from
               real DEM + OSM graph + WorldPop + BBMP at each projected water level.

Sub-hourly meteorological forecasts are NOT available from OWM free tier.
All extrapolation assumptions are labelled explicitly in the response.
"""
import logging
import time
from typing import Optional

import networkx as nx
from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import JSONResponse

from app.graph_pipeline.graph_build import GraphStore
from app.simulation.topography import flood_ablate, get_elevation_bounds
from app.data.population import query_population_nodes
from app.data.backtest import DEM_MIN_M, URBAN_RUNOFF_COEFFICIENT
from app.simulation.temporal_projection import build_temporal_projection
from app.integrations.weather import fetch_current_weather, fetch_forecast_rain
from app.api.accessibility import _snap_to_graph, _get_affected_wards

logger = logging.getLogger(__name__)
router = APIRouter()


async def _compute_network_impact(G: nx.Graph, water_level_m: float) -> dict:
    """Compute flood impact on the road network at a given water level."""
    flooded = flood_ablate(G, water_level_m)
    flooded_set = set(flooded)
    total_nodes = G.number_of_nodes()

    road_length_m = sum(
        d.get("length", 0)
        for u, v, d in G.edges(data=True)
        if u in flooded_set or v in flooded_set
    )

    pop_result = query_population_nodes(G, flooded)

    # Ward impact
    ward_counts = _get_affected_wards(G, flooded)
    wards_with_flood = {w: c for w, c in ward_counts.items() if w != "Outside Ward Boundary"}

    # Network connectivity of surviving subgraph
    surviving = [n for n in G.nodes() if n not in flooded_set]
    if surviving:
        Gs = G.subgraph(surviving)
        n_components = nx.number_connected_components(Gs)
        lcc_size = len(max(nx.connected_components(Gs), key=len))
    else:
        n_components = 0
        lcc_size = 0

    return {
        "water_level_m":            water_level_m,
        "flooded_nodes":            len(flooded),
        "total_nodes":              total_nodes,
        "flood_fraction_pct":       round(len(flooded) / total_nodes * 100, 2) if total_nodes else 0,
        "road_length_flooded_km":   round(road_length_m / 1000, 2),
        "population_in_flood_zone": {
            "value":  pop_result.get("population", 0),
            "source": pop_result.get("source", "unknown"),
            "note":   "WorldPop 2020 100m gridded estimate — not census-verified.",
        },
        "wards_affected":           len(wards_with_flood),
        "surviving_components":     n_components,
        "lcc_surviving_nodes":      lcc_size,
    }


@router.get("/temporal-projection")
async def temporal_flood_projection(
    base_water_level_m: Optional[float] = Query(
        default=None,
        description=(
            "Optional: current water level (m ASL) to use as the NOW baseline. "
            "If omitted, the DEM minimum (877m) is used — representing a dry baseline. "
            "Supply the last flood result level for active-event projection."
        ),
    ),
    override_rainfall_mm_h: Optional[float] = Query(
        default=None,
        description=(
            "Optional: override the observed rainfall rate (mm/h) for sensitivity analysis. "
            "If omitted, the live OWM rain.1h value is used. "
            "Must be >= 0. Clearly labelled as override in the response."
        ),
    ),
):
    """
    Temporal flood projection: NOW → +30min → +60min → +90min.

    Fetches the current observed rainfall rate from OpenWeatherMap.
    Extrapolates forward using linear rainfall-persistence.
    Runs the DEM inundation model at each projected water level.
    All assumptions and limitations are explicitly labelled.
    """
    G = GraphStore.get_healed() or GraphStore.get_osm_fallback()
    if G is None:
        raise HTTPException(status_code=503, detail="No road graph available.")

    bounds = get_elevation_bounds(G)

    # ── Fetch live weather ──────────────────────────────────────────────────────
    t0 = time.monotonic()
    weather = await fetch_current_weather()
    weather_ok = "error" not in weather

    forecast = await fetch_forecast_rain(hours=3)
    forecast_ok = "error" not in forecast

    # ── Determine observed rainfall rate ───────────────────────────────────────
    if override_rainfall_mm_h is not None:
        if override_rainfall_mm_h < 0:
            raise HTTPException(
                status_code=400,
                detail="override_rainfall_mm_h must be >= 0."
            )
        rainfall_rate_mm_h = override_rainfall_mm_h
        rainfall_source = f"user_override_{override_rainfall_mm_h}mm_h"
        rainfall_note = (
            f"User-supplied rainfall rate of {override_rainfall_mm_h}mm/h "
            "(overrides live OWM value). Use for sensitivity analysis only."
        )
    elif weather_ok:
        rainfall_rate_mm_h = float(weather.get("current_rainfall_1h_mm", 0.0))
        rainfall_source = "OpenWeatherMap_Current_Weather_API_rain.1h"
        rainfall_note = (
            "rain.1h = OWM-measured precipitation in the past 1 hour. "
            "Used as current rainfall rate (mm/h) for linear persistence extrapolation."
        )
    else:
        rainfall_rate_mm_h = 0.0
        rainfall_source = "unavailable"
        rainfall_note = f"OWM API unavailable: {weather.get('error')}. Rainfall rate set to 0 mm/h."

    # ── Determine base water level ─────────────────────────────────────────────
    if base_water_level_m is not None:
        if not (bounds["min"] <= base_water_level_m <= bounds["max"]):
            raise HTTPException(
                status_code=400,
                detail=(
                    f"base_water_level_m={base_water_level_m} outside DEM range "
                    f"[{bounds['min']}, {bounds['max']}]."
                ),
            )
        actual_base = base_water_level_m
        base_note = f"User-supplied base water level: {base_water_level_m}m ASL."
    else:
        # Use last flood result if available; otherwise DEM min (dry baseline)
        last_flood = GraphStore.get_last_flood_result()
        if last_flood and "water_level" in last_flood:
            actual_base = float(last_flood["water_level"])
            base_note = (
                f"Base level from last flood simulation: {actual_base}m ASL "
                f"(scenario: {last_flood.get('scenario', 'unknown')})."
            )
        else:
            actual_base = bounds["min"]
            base_note = (
                f"No active flood result. Using DEM minimum ({bounds['min']}m) as dry baseline. "
                "Run a flood simulation first for active-event projection."
            )

    # ── Build temporal projection ──────────────────────────────────────────────
    next_3h = None
    if forecast_ok and forecast.get("forecast_items"):
        next_3h = forecast["forecast_items"][0].get("rain_3h_mm", 0.0)

    # Pre-fetch hospitals for consequence tracking
    from app.integrations.overpass import fetch_facilities
    try:
        hospitals = await fetch_facilities(south=12.92, west=77.57, north=12.99, east=77.64, amenities=["hospital", "clinic", "health_post"])
        hospital_nodes = _snap_to_graph(G, hospitals)
    except Exception:
        hospital_nodes = []

    # Helper for full impact
    from app.simulation.topography import flood_ablate
    from app.api.historical import _get_affected_wards
    from app.simulation.resilience import compute_resilience_index
    from app.data.population import query_population_nodes
    import networkx as nx

    # Per-request caches keyed by the FROZENSET of flooded node IDs.
    # This is provably correct: same key → identical flooded set → identical results.
    # (Previously keyed by count, which could theoretically collide if two water levels
    # produce the same count but different sets — impossible under monotone bathtub model,
    # but using the actual set makes this invariant explicit and verifiable.)
    _pop_cache: dict = {}
    _resilience_cache: dict = {}
    _road_len_cache: dict = {}
    _ward_cache: dict = {}
    _components_cache: dict = {}
    _hospitals_cache: dict = {}

    async def _compute_full_impact(G_base: nx.Graph, water_level_m: float) -> dict:
        flooded_ids = flood_ablate(G_base, water_level_m)
        flooded_set = set(flooded_ids)
        # Use frozenset hash as cache key — identical flooded set → identical cache key
        cache_key = frozenset(flooded_ids)

        # ── Resilience (most expensive: ~8-10s Dijkstra from 60 sources)
        if cache_key in _resilience_cache:
            ri = _resilience_cache[cache_key]
            surviving_components = _components_cache[cache_key]
        else:
            G_damaged = G_base.copy()
            G_damaged.remove_nodes_from(flooded_ids)
            ri = compute_resilience_index(G_base, G_damaged)["resilience_index"]
            surviving_components = nx.number_connected_components(G_damaged) if G_damaged.number_of_nodes() > 0 else 0
            _resilience_cache[cache_key] = ri
            _components_cache[cache_key] = surviving_components

        # ── Population: spatial WorldPop raster intersection
        if cache_key in _pop_cache:
            pop_result = _pop_cache[cache_key]
        else:
            pop_result = query_population_nodes(G_base, flooded_ids)
            _pop_cache[cache_key] = pop_result

        # ── Road length in metres (use 'length', not 'weight')
        if cache_key in _road_len_cache:
            road_len_m = _road_len_cache[cache_key]
        else:
            road_len_m = 0.0
            for u, v, k, d in G_base.edges(keys=True, data=True):
                if u in flooded_set or v in flooded_set:
                    road_len_m += d.get("length", 0)
            _road_len_cache[cache_key] = road_len_m

        # ── Ward impact
        if cache_key in _ward_cache:
            wards = _ward_cache[cache_key]
        else:
            wards = _get_affected_wards(G_base, flooded_ids)
            _ward_cache[cache_key] = wards

        # ── Hospital impact
        if cache_key in _hospitals_cache:
            hospitals_flooded = _hospitals_cache[cache_key]
        else:
            hospitals_flooded = sum(1 for hn in hospital_nodes if hn in flooded_set)
            _hospitals_cache[cache_key] = hospitals_flooded

        
        return {
            "flooded_nodes": len(flooded_ids),
            "road_length_flooded_km": round(road_len_m / 1000, 2),
            "wards_affected": wards,
            "population_in_flood_zone": {
                "value": pop_result.get("population", 0),
                "source": pop_result.get("source", "unknown"),
                "methodology": pop_result.get("estimation_method", "unknown"),
                "note": pop_result.get("note", "WorldPop 2020 100m gridded estimate — not census-verified."),
                "uncertainty_note": pop_result.get("uncertainty_note", ""),
            },
            "surviving_components": surviving_components,
            "hospitals_flooded": hospitals_flooded,
            "total_hospitals": len(hospital_nodes),
            "resilience_index": ri,
        }


    projection = build_temporal_projection(
        current_rainfall_1h_mm=rainfall_rate_mm_h,
        base_water_level_m=actual_base,
        dem_min_m=bounds["min"],
        runoff_coefficient=URBAN_RUNOFF_COEFFICIENT,
        next_3h_rain_mm=next_3h,
        observed_source=rainfall_source,
    )

    # ── Run DEM inundation at each projected water level ──────────────────────
    enriched_horizons = []
    baseline_impact = None

    for idx, h in enumerate(projection["horizons"]):
        wl = h["projected_water_level_m"]
        wl_clamped = min(wl, bounds["max"])
        clamped = wl > bounds["max"]

        impact = await _compute_full_impact(G, wl_clamped)
        impact["water_level_clamped_to_dem_max"] = clamped
        
        if idx == 0:
            baseline_impact = impact
            consequence_note = "Baseline network state."
            status = "STABLE"
        else:
            node_diff = impact["flooded_nodes"] - baseline_impact["flooded_nodes"]
            ri_diff = baseline_impact["resilience_index"] - impact["resilience_index"]
            hosp_diff = impact["hospitals_flooded"] - baseline_impact["hospitals_flooded"]
            
            if node_diff == 0 and ri_diff < 0.01:
                consequence_note = (
                    f"No new network failures. The incremental water depth "
                    f"(+{h['additional_water_depth_mm']}mm) is too small to trigger "
                    f"new topological thresholds at 30m DEM resolution."
                )
                status = "STABLE"
            else:
                consequence_note = f"Incremental water depth triggered {node_diff} new flooded nodes. Resilience dropped by {ri_diff:.3f}."
                status = "CRITICAL" if (ri_diff > 0.10 or hosp_diff > 0) else "DEGRADING"

        if clamped:
            impact["clamp_note"] = (
                f"Projected level {wl}m exceeds DEM max {bounds['max']}m. "
                "Clamped to DEM max for simulation."
            )

        enriched_horizons.append({
            **h, 
            "network_impact": impact,
            "network_consequences_note": consequence_note
        })

    elapsed_ms = round((time.monotonic() - t0) * 1000, 1)

    result = {
        # ── Methodology declaration ────────────────────────────────────────────
        "methodology": {
            "model":              "linear_rainfall_persistence_extrapolation_plus_DEM_inundation",
            "data_limitation":    projection["data_limitation"],
            "observed_source":    rainfall_source,
            "rainfall_rate_note": projection["rainfall_rate_note"],
            "labels_guide": {
                "OBSERVED":     "Measured data from OWM API (past hour rainfall).",
                "EXTRAPOLATED": "Linear persistence: current rate × time × RC. NOT a meteorological forecast.",
                "MODELED":      "DEM height-threshold inundation + OSM graph + WorldPop at each projected level.",
            },
        },

        # ── Live observed conditions ───────────────────────────────────────────
        "observed_conditions": {
            "_section":             "OBSERVED",
            "rainfall_rate_mm_h":   round(rainfall_rate_mm_h, 2),
            "rainfall_source":      rainfall_source,
            "rainfall_note":        rainfall_note,
            "temperature_c":        weather.get("temperature_c") if weather_ok else None,
            "humidity_pct":         weather.get("humidity_pct") if weather_ok else None,
            "description":          weather.get("description") if weather_ok else None,
            "risk":                 weather.get("risk") if weather_ok else None,
            "weather_api_ok":       weather_ok,
            "weather_api_error":    weather.get("error") if not weather_ok else None,
        },

        # ── Base state ─────────────────────────────────────────────────────────
        "base_state": {
            "base_water_level_m": actual_base,
            "base_note":          base_note,
            "dem_range": {
                "min_m":  bounds["min"],
                "max_m":  bounds["max"],
                "mean_m": bounds["mean"],
            },
            "override_rainfall_used": override_rainfall_mm_h is not None,
            "override_base_used":     base_water_level_m is not None,
        },

        # ── Temporal horizons ──────────────────────────────────────────────────
        "temporal_horizons": enriched_horizons,

        # ── Next 3h OWM forecast (earliest available future data) ──────────────
        "next_3h_owm_forecast": projection.get("next_3h_forecast"),

        # ── Performance ────────────────────────────────────────────────────────
        "computation_ms": elapsed_ms,
    }

    # Store for Copilot context — use the NOW horizon (baseline observed state)
    # Include all computed impact metrics so Copilot has full situational awareness
    now_impact = enriched_horizons[0]["network_impact"] if enriched_horizons else {}
    pop_now = now_impact.get("population_in_flood_zone", {})
    GraphStore.set_last_flood_result({
        "scenario":                  "temporal_projection",
        "water_level":               actual_base,
        "rainfall_rate_mm_h":        rainfall_rate_mm_h,
        "horizons_computed":         len(enriched_horizons),
        "data_type":                 "TEMPORAL_PROJECTION",
        # NOW-horizon impact metrics for Copilot grounding
        "flooded_nodes_count":       now_impact.get("flooded_nodes", 0),
        "road_length_flooded_km":    now_impact.get("road_length_flooded_km", 0),
        "population_in_flood_zone":  pop_now.get("value", 0) if isinstance(pop_now, dict) else pop_now,
        "wards_affected":            now_impact.get("wards_affected", {}),
        "hospitals_in_flood_zone":   now_impact.get("hospitals_flooded", 0),
    })

    logger.info(
        f"Temporal projection complete: base={actual_base}m, "
        f"rain={rainfall_rate_mm_h}mm/h, {len(enriched_horizons)} horizons in {elapsed_ms}ms"
    )

    return JSONResponse(result)
