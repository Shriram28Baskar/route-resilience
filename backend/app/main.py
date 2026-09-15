"""
Route Resilience — FastAPI backend entrypoint.
Mounts all sub-routers and configures CORS, lifespan, and logging.

AMDIROS Autonomous Loop:
  The loop runs every POLL_INTERVAL_S seconds (unconditional observation).
  Only one state transition executes at a time via _LOOP_LOCK (asyncio.Lock).
  This serialises all three trigger paths:
    1. Autonomous scheduler (every POLL_INTERVAL_S)
    2. POST /simulate/trigger-loop (manual, demo control)
    3. Citizen report with flooding_indicator=True (immediate re-evaluation)
"""
import asyncio
import logging
import os
import time as _time
from contextlib import asynccontextmanager
from datetime import datetime, timezone

import networkx as nx
from dotenv import load_dotenv
load_dotenv()  # Load environment variables from .env before imports

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.api import (
    segmentation, graph, simulation, accessibility,
    copilot, reports, bhuvan,
    alerts as alerts_router, historical, temporal,
)
from app.api import citizens as citizens_router
from app.graph_pipeline.graph_build import GraphStore

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
)
logger = logging.getLogger(__name__)

# ── Autonomous loop configuration ─────────────────────────────────────────────
# No LOOP_TRIGGER_MM — the loop is unconditional. evaluate_delta() decides
# whether to proceed to PREDICT/DECIDE/ACT.
POLL_INTERVAL_S: int = int(os.getenv("POLL_INTERVAL_S", "60"))  # demo cadence

# ── Serialization: only one state transition at a time ────────────────────────
# All three trigger paths (scheduler / manual / citizen) acquire this lock.
# Ensures sequence numbers, prev_state, ring-buffer ordering, and WS
# broadcasts remain deterministic and race-free.
_LOOP_LOCK: asyncio.Lock | None = None   # initialised inside lifespan (event loop exists)
_MANUAL_TRIGGER: asyncio.Event | None = None
_CITIZEN_TRIGGER: asyncio.Event | None = None
_MANUAL_RAINFALL_OVERRIDE: float | None = None
_IS_FIRST_ACTIVATION: bool = True


def get_loop_lock() -> asyncio.Lock:
    """Return the module-level loop lock."""
    global _LOOP_LOCK
    if _LOOP_LOCK is None:
        _LOOP_LOCK = asyncio.Lock()
    return _LOOP_LOCK


def get_manual_trigger() -> asyncio.Event:
    global _MANUAL_TRIGGER
    if _MANUAL_TRIGGER is None:
        _MANUAL_TRIGGER = asyncio.Event()
    return _MANUAL_TRIGGER


def get_citizen_trigger() -> asyncio.Event:
    global _CITIZEN_TRIGGER
    if _CITIZEN_TRIGGER is None:
        _CITIZEN_TRIGGER = asyncio.Event()
    return _CITIZEN_TRIGGER


def set_manual_rainfall_override(val: float | None):
    global _MANUAL_RAINFALL_OVERRIDE
    _MANUAL_RAINFALL_OVERRIDE = val


def get_manual_rainfall_override() -> float | None:
    return _MANUAL_RAINFALL_OVERRIDE


# ── The observation cycle ──────────────────────────────────────────────────────

async def run_observation_cycle(is_first_activation: bool) -> bool:
    """
    Execute one full OBSERVE → FUSE → UNDERSTAND → PREDICT → DECIDE → ACT cycle.

    Must be called with _LOOP_LOCK held by the caller.
    Returns True if a material change was detected and state was broadcast.
    """
    global _IS_FIRST_ACTIVATION
    t0 = _time.perf_counter()

    from app.simulation.disaster_state import (
        DisasterState, NodeETA, HospStatus, state_ring_buffer,
        citizen_evidence_store, state_to_ws_dict, heartbeat_dict,
        build_template_narrative,
    )
    from app.simulation.decision_engine import (
        evaluate_delta, build_action_plan, should_invoke_llm,
    )
    from app.simulation.projected_flood_exposure import predict_flood_exposure_eta
    from app.simulation.evacuation_advisory import generate_evacuation_advisories
    from app.simulation.topography import flood_ablate, flood_ablate_basin_aware
    from app.simulation.resilience import compute_resilience_index
    from app.simulation.routing import compute_relief_camps
    from app.data.backtest import rainfall_to_water_level
    from app.api.accessibility import _get_affected_wards
    from app.data.population import query_population_nodes
    from app.integrations.weather import fetch_current_weather
    from app.integrations.overpass import fetch_facilities
    from app.api.accessibility import _snap_to_graph
    from app.graph_pipeline.graph_build import GraphStore
    from app.integrations.alerts import broadcast_disaster_state, broadcast_heartbeat, dispatch_alert

    seq = state_ring_buffer.next_seq()
    observed_at = datetime.now(timezone.utc).isoformat()

    # ── OBSERVE ───────────────────────────────────────────────────────────────
    try:
        weather = await fetch_current_weather()
    except Exception as exc:
        logger.warning(f"Loop #{seq}: OWM fetch failed ({exc}) — retaining previous state.")
        prev = state_ring_buffer.get_latest()
        await broadcast_heartbeat(heartbeat_dict(
            seq, observed_at, 0.0, prev.sequence_no if prev else 0
        ))
        return False

    if "error" in weather:
        logger.warning(f"Loop #{seq}: OWM error ({weather['error']}) — retaining previous state.")
        prev = state_ring_buffer.get_latest()
        await broadcast_heartbeat(heartbeat_dict(
            seq, observed_at, 0.0, prev.sequence_no if prev else 0
        ))
        return False

    rainfall_rate_mm_h = float(weather.get("current_rainfall_1h_mm", 0.0))
    if _MANUAL_RAINFALL_OVERRIDE is not None:
        rainfall_rate_mm_h = float(_MANUAL_RAINFALL_OVERRIDE)
        logger.info(f"Loop #{seq}: Using demo manual rainfall override: {rainfall_rate_mm_h} mm/h")

    # ── FUSE ──────────────────────────────────────────────────────────────────
    G = GraphStore.get_osm_fallback()
    if G is None:
        logger.warning(f"Loop #{seq}: Graph not loaded — skipping cycle.")
        return False

    # Basin-aware flood ablation: each node is compared against its own
    # drainage basin's minimum elevation, not a city-wide bathtub level.
    # Fallback: global water level if basin-aware function fails.
    try:
        flooded_nodes = flood_ablate_basin_aware(G, rainfall_rate_mm_h)
        wl_result = rainfall_to_water_level(rainfall_rate_mm_h)   # kept for reporting
    except Exception as exc:
        logger.warning(f"Loop #{seq}: Basin-aware flood failed ({exc}) — using global bathtub fallback.")
        wl_result = rainfall_to_water_level(rainfall_rate_mm_h)
        flooded_nodes = flood_ablate(G, wl_result.get("water_level_m", 877.0))

    water_level_m = wl_result.get("water_level_m", 877.0)
    flooded_set = set(flooded_nodes)

    # Build alive subgraph
    from app.simulation.scenarios import ablate_nodes  # reuse existing helper
    G_alive = ablate_nodes(G, flooded_nodes)

    # ── UNDERSTAND ────────────────────────────────────────────────────────────
    async def _async_ri():
        try:
            return await asyncio.to_thread(compute_resilience_index, G, G_alive, 30)
        except Exception as exc:
            logger.warning(f"Loop #{seq}: RI compute failed ({exc})")
            return {"resilience_index": None, "partition_count": 1}

    async def _async_hospitals():
        status = []
        try:
            s, w, n, e = 12.92, 77.57, 12.99, 77.64
            hospitals_raw = await asyncio.wait_for(
                fetch_facilities(s, w, n, e, amenities=["hospital", "clinic", "health_post"]),
                timeout=5.0,
            )
            hosp_nodes = _snap_to_graph(G, hospitals_raw)
            comps = list(nx.connected_components(G_alive))
            largest_comp = max(comps, key=len) if comps else set()
            for idx, node_id in enumerate(hosp_nodes):
                h = hospitals_raw[idx] if idx < len(hospitals_raw) else {}
                reachable = (node_id in largest_comp) and (node_id not in flooded_set)
                status.append(HospStatus(
                    name=h.get("name", f"Hospital-{node_id}"),
                    lat=h.get("lat", 0.0),
                    lon=h.get("lon", 0.0),
                    node_id=node_id,
                    reachable=reachable,
                    travel_time_s=None,
                ))
        except Exception as exc:
            logger.warning(f"Loop #{seq}: Hospital status fetch failed ({exc}) — using cached or empty.")
        return status

    async def _async_pop():
        try:
            # Latency SLA guard: Shapely unary_union on >600 edges exceeds 3s budget
            if len(flooded_nodes) > 600:
                return int(len(flooded_nodes) * 120)
            pop_res = await asyncio.wait_for(
                asyncio.to_thread(query_population_nodes, G, flooded_nodes),
                timeout=3.0,
            )
            return int(pop_res.get("population") or (len(flooded_nodes) * 120))
        except Exception as exc:
            logger.warning(f"Loop #{seq}: Population query degraded ({exc}) — using node proxy.")
            return int(len(flooded_nodes) * 120)

    ri_task = asyncio.create_task(_async_ri())
    hosp_task = asyncio.create_task(_async_hospitals())
    pop_task = asyncio.create_task(_async_pop())
    ward_flood_counts = _get_affected_wards(G, flooded_nodes)
    affected_wards = [w for w in ward_flood_counts if w != "Outside Ward Boundary"]

    ri_result, hospital_status, population_at_risk = await asyncio.gather(ri_task, hosp_task, pop_task)
    resilience_index = ri_result.get("resilience_index")
    partition_count = ri_result.get("partition_count", 1)

    # Drain citizen evidence (independent evidence layer)
    pending_citizen_reports = citizen_evidence_store.drain()

    # Build partial state for change gate
    partial_state = DisasterState(
        sequence_no=seq,
        observed_at=observed_at,
        loop_duration_s=0.0,
        partial=True,
        rainfall_rate_mm_h=rainfall_rate_mm_h,
        water_level_m=water_level_m,
        flooded_node_count=len(flooded_nodes),
        resilience_index=resilience_index,
        partition_count=partition_count,
        affected_wards=affected_wards,
        hospital_status=hospital_status,
        population_at_risk=population_at_risk,
        citizen_reports=pending_citizen_reports,
        predicted_flood_exposure=[],
        action_plan=None,
        narrative="",
        narrative_source="template",
        material_change=False,
        decision_event=None,
        flooded_node_ids=[str(n) for n in flooded_nodes],
    )

    # ── MATERIAL CHANGE GATE ──────────────────────────────────────────────────
    prev_state = state_ring_buffer.get_latest()
    is_material, severity, trigger_reason, changed_components = evaluate_delta(
        prev_state, partial_state
    )

    if not is_material and not pending_citizen_reports:
        logger.info(f"Loop #{seq}: No material change — broadcasting heartbeat.")
        prev = state_ring_buffer.get_latest()
        await broadcast_heartbeat(heartbeat_dict(
            seq, observed_at, rainfall_rate_mm_h,
            prev.sequence_no if prev else 0,
        ))
        return False

    # ── PREDICT ───────────────────────────────────────────────────────────────
    try:
        flood_exposure_raw = predict_flood_exposure_eta(G_alive, water_level_m, rainfall_rate_mm_h)
        predicted_flood_exposure = [
            NodeETA(
                node_id=r["node_id"],
                lat=r["lat"] or 0.0,
                lon=r["lon"] or 0.0,
                elevation_m=r["elevation_m"],
                current_water_level_m=r["current_water_level_m"],
                delta_elevation_m=r["delta_elevation_m"],
                eta_minutes=r["eta_minutes"],
                risk_label=r["risk_label"],
                data_type=r["data_type"],
                projection_basis=r["projection_basis"],
                methodology_note=r.get("methodology_note", ""),
            )
            for r in flood_exposure_raw
        ]
    except Exception as exc:
        logger.warning(f"Loop #{seq}: Flood exposure prediction failed ({exc})")
        predicted_flood_exposure = []

    # ── DECIDE (all deterministic) ────────────────────────────────────────────
    async def _async_camps():
        try:
            return await asyncio.to_thread(compute_relief_camps, G_alive, 3)
        except Exception as exc:
            logger.warning(f"Loop #{seq}: Relief camps failed ({exc})")
            return {"camps": []}

    async def _async_prescriptions():
        from app.simulation.recommendations import generate_dynamic_prescriptions, get_cached_recommendations
        try:
            return await asyncio.to_thread(
                generate_dynamic_prescriptions, G_alive, flooded_nodes, ri_result or {}, G
            )
        except Exception as exc:
            logger.warning(f"Loop #{seq}: Dynamic prescriptions failed ({exc}) — using cached.")
            return get_cached_recommendations()

    camps_task = asyncio.create_task(_async_camps())
    presc_task = asyncio.create_task(_async_prescriptions())
    camps_result, prescriptions = await asyncio.gather(camps_task, presc_task)

    try:
        advisories = generate_evacuation_advisories(
            G_alive, flooded_nodes, ward_flood_counts,
            camps_result.get("camps", []), hospital_status, resilience_index,
        )
    except Exception as exc:
        logger.warning(f"Loop #{seq}: Evacuation advisories failed ({exc})")
        advisories = []

    from app.simulation.disaster_state import DecisionEvent
    decision_event = DecisionEvent(
        severity=severity,
        trigger_reason=trigger_reason,
        changed_components=changed_components,
        previous_seq=prev_state.sequence_no if prev_state else 0,
        new_seq=seq,
    )

    action_plan = build_action_plan(
        sequence_no=seq,
        camps_result=camps_result,
        advisories=advisories,
        prescriptions=prescriptions,
        hospital_status=hospital_status,
        population_at_risk=population_at_risk,
        resilience_index=resilience_index,
        affected_wards=affected_wards,
    )

    # ── ACT — narrative ───────────────────────────────────────────────────────
    loop_duration_s = _time.perf_counter() - t0
    final_state = DisasterState(
        sequence_no=seq,
        observed_at=observed_at,
        loop_duration_s=round(loop_duration_s, 2),
        partial=False,
        rainfall_rate_mm_h=rainfall_rate_mm_h,
        water_level_m=water_level_m,
        flooded_node_count=len(flooded_nodes),
        resilience_index=resilience_index,
        partition_count=partition_count,
        affected_wards=affected_wards,
        hospital_status=hospital_status,
        population_at_risk=population_at_risk,
        citizen_reports=pending_citizen_reports,
        predicted_flood_exposure=predicted_flood_exposure,
        action_plan=action_plan,
        narrative="",
        narrative_source="template",
        material_change=True,
        decision_event=decision_event,
        flooded_node_ids=[str(n) for n in flooded_nodes],
    )

    if should_invoke_llm(severity, is_first_activation):
        try:
            from app.api.copilot import generate_incident_narrative
            narrative = await asyncio.wait_for(
                generate_incident_narrative(final_state),
                timeout=10.0,
            )
            if narrative and len(narrative.strip()) > 0:
                final_state.narrative = narrative.strip()
                final_state.narrative_source = "llm"
            else:
                final_state.narrative = build_template_narrative(final_state)
                final_state.narrative_source = "template"
        except Exception as exc:
            logger.warning(f"Loop #{seq}: LLM narrative failed ({exc}) — using template.")
            final_state.narrative = build_template_narrative(final_state)
            final_state.narrative_source = "template"
    else:
        final_state.narrative = build_template_narrative(final_state)
        final_state.narrative_source = "template"

    # ── ACT — commit and broadcast ─────────────────────────────────────────────
    state_ring_buffer.push(final_state)
    await broadcast_disaster_state(state_to_ws_dict(final_state))

    if severity == "HIGH" and any(not h.reachable for h in hospital_status):
        try:
            isolated = [h.name for h in hospital_status if not h.reachable]
            await dispatch_alert(
                severity="critical",
                title="Hospital Isolation Detected",
                message=f"Hospital(s) now isolated from road network: {', '.join(isolated)}",
                details={
                    "loop_sequence": seq,
                    "water_level_m": water_level_m,
                    "hospitals_isolated": ", ".join(isolated),
                    "wards_affected": ", ".join(affected_wards),
                },
                send_email=True,
                send_ws=False,  # state already broadcast above
            )
        except Exception as exc:
            logger.warning(f"Loop #{seq}: Alert dispatch failed ({exc})")

    _IS_FIRST_ACTIVATION = False

    logger.info(
        f"Loop #{seq} complete in {loop_duration_s:.2f}s — "
        f"material_change=True, severity={severity}, "
        f"flooded={len(flooded_nodes)}, RI={resilience_index}, "
        f"narrative_source={final_state.narrative_source}"
    )
    return True


async def autonomous_disaster_loop():
    """
    Unconditional observation loop.

    Runs every POLL_INTERVAL_S seconds regardless of rainfall or previous state.
    Each iteration acquires _LOOP_LOCK before executing, serialising all trigger paths.

    The loop never crashes the server — exceptions are caught, logged, and the loop
    continues to the next interval.
    """
    global _IS_FIRST_ACTIVATION
    logger.info(f"🔄 Autonomous loop starting — interval: {POLL_INTERVAL_S}s")

    while True:
        # Wait for interval OR manual/citizen trigger (whichever fires first)
        try:
            from app.simulation.loop_triggers import wait_for_loop_wakeup
            await wait_for_loop_wakeup(
                _MANUAL_TRIGGER, _CITIZEN_TRIGGER, POLL_INTERVAL_S,
            )
        except Exception:
            logger.exception("Autonomous loop wait failed; retrying after interval")
            await asyncio.sleep(POLL_INTERVAL_S)

        # Clear event flags regardless of which trigger fired
        _MANUAL_TRIGGER.clear()
        _CITIZEN_TRIGGER.clear()

        # Serialise: only one cycle runs at a time
        async with _LOOP_LOCK:
            try:
                await run_observation_cycle(is_first_activation=_IS_FIRST_ACTIVATION)
            except Exception as exc:
                logger.error(f"Autonomous loop cycle error (non-fatal): {exc}", exc_info=True)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup / shutdown lifecycle hook."""
    global _LOOP_LOCK, _MANUAL_TRIGGER, _CITIZEN_TRIGGER

    logger.info("🚀 Route Resilience backend starting up …")

    # Initialise loop synchronisation primitives (must be inside async context)
    _LOOP_LOCK = asyncio.Lock()
    _MANUAL_TRIGGER = asyncio.Event()
    _CITIZEN_TRIGGER = asyncio.Event()

    # Pre-warm graph store (loads OSM fallback if available)
    await GraphStore.initialize()

    # Stamp terrain before the autonomous loop starts.  This keeps initial DEM
    # interpolation out of the critical observation-cycle latency budget.
    G = GraphStore.get_osm_fallback()
    if G is not None:
        from app.simulation.topography import initialize_elevations
        initialize_elevations(G)
        # Compute per-basin DEM_MIN from actual node elevations (requires elevation stamps)
        from app.data.backtest import initialize_basin_mins
        initialize_basin_mins(G)

    # Pre-compute metrics and centrality for the OSM fallback graph in a background thread
    import threading
    from app.graph_pipeline.centrality import compute_betweenness
    from app.graph_pipeline.metrics import compute_graph_metrics

    def precompute_osm():
        import time
        G = GraphStore.get_osm_fallback()
        if G is None:
            return

        logger.info("Warmup: Starting background OSM graph metrics precompute ...")
        compute_graph_metrics(G)

        from app.graph_pipeline.centrality import compute_closeness, get_articulation_points, compute_edge_betweenness

        logger.info("Warmup: Starting background OSM betweenness centrality (k=50) precompute ...")
        t0 = time.perf_counter()
        compute_betweenness(G, k=50)
        elapsed_bc = time.perf_counter() - t0
        logger.info(
            f"Warmup: Betweenness centrality complete in {elapsed_bc:.2f}s "
            f"[Brandes k=50, {G.number_of_nodes():,} nodes, {G.number_of_edges():,} edges]"
        )

        logger.info("Warmup: Starting background OSM closeness centrality precompute ...")
        compute_closeness(G)

        logger.info("Warmup: Starting background OSM articulation points precompute ...")
        t1 = time.perf_counter()
        get_articulation_points(G)
        elapsed_ap = time.perf_counter() - t1
        logger.info(f"Warmup: Articulation points complete in {elapsed_ap:.2f}s")

        logger.info("Warmup: Starting background OSM edge betweenness (k=50) precompute ...")
        compute_edge_betweenness(G, k=50)

        # ── Pre-compute recommendations (never change for static OSM graph) ──
        logger.info("Warmup: Pre-computing infrastructure recommendations ...")
        t2 = time.perf_counter()
        try:
            from app.simulation.recommendations import (
                cache_recommendations, generate_recommendations,
            )
            cache_recommendations(generate_recommendations(G))
            logger.info(f"Warmup: Recommendations cached in {time.perf_counter()-t2:.2f}s")
        except Exception as exc:
            logger.warning(f"Warmup: Recommendations pre-compute failed: {exc}")

        # ── Pre-compute predefined scenario results (static — same graph every time) ──
        logger.info("Warmup: Pre-computing predefined scenario results ...")
        t3 = time.perf_counter()
        try:
            centrality_scores = compute_betweenness(G, k=50)
            ranked = sorted(centrality_scores.items(), key=lambda x: x[1], reverse=True)
            gatekeepers = [str(nid) for nid, _ in ranked[:10]]
            from app.simulation.scenarios import run_multi_scenario
            from app.api.simulation import _SCENARIO_CACHE
            predefined = [
                {"name": "Baseline",        "description": "Normal operations, no disruptions",        "ablated_node_ids": []},
                {"name": "Minor Incident",  "description": "Isolated road closure",                    "ablated_node_ids": gatekeepers[:1]},
                {"name": "Major Flood",     "description": "Corridor flooding",                        "ablated_node_ids": gatekeepers[:5]},
                {"name": "Targeted Attack", "description": "Coordinated failure of key intersections", "ablated_node_ids": gatekeepers[:10]},
            ]
            _SCENARIO_CACHE["predefined"] = run_multi_scenario(G, predefined)
            logger.info(f"Warmup: Predefined scenarios cached in {time.perf_counter()-t3:.2f}s")
        except Exception as exc:
            logger.warning(f"Warmup: Scenario pre-compute failed: {exc}")

        logger.info(
            f"Warmup: All pre-computation complete! "
            f"[Betweenness={elapsed_bc:.2f}s, APs={elapsed_ap:.2f}s] "
            f"on {G.number_of_nodes():,}-node Bengaluru OSM graph"
        )

    threading.Thread(target=precompute_osm, daemon=True).start()

    # Start autonomous loop
    loop_task = asyncio.create_task(autonomous_disaster_loop(), name="autonomous_loop")

    yield

    loop_task.cancel()
    try:
        await loop_task
    except asyncio.CancelledError:
        pass
    logger.info("👋 Route Resilience backend shutting down …")


app = FastAPI(
    title="Route Resilience API",
    description=(
        "Autonomous Multimodal Disaster Intelligence & Response OS. "
        "Built on real geospatial, terrain, weather and population data "
        "(OSM, SRTMGL1 DEM, OpenWeatherMap, WorldPop, IMD), with explicitly "
        "labeled simulation and extrapolation where real-time operational data "
        "is unavailable."
    ),
    version="2.0.0",
    lifespan=lifespan,
)

# ── CORS ──────────────────────────────────────────────────────────────────────
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000", "http://127.0.0.1:3000",
        "ws://localhost:3000",   "ws://127.0.0.1:3000",
        "http://localhost:8000", "http://127.0.0.1:8000",
    ],
    allow_origin_regex=r"http://(localhost|127\.0\.0\.1)(:[0-9]+)?",
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Routers ───────────────────────────────────────────────────────────────────
app.include_router(segmentation.router, prefix="/segment",            tags=["Segmentation"])
app.include_router(graph.router,        prefix="/graph",              tags=["Graph"])
app.include_router(simulation.router,   prefix="/simulate",           tags=["Simulation"])
app.include_router(historical.router,   prefix="/simulate/historical",tags=["Historical Scenarios"])
app.include_router(temporal.router,     prefix="/simulate",           tags=["Temporal Projection"])
app.include_router(accessibility.router,prefix="/accessibility",      tags=["Accessibility"])
app.include_router(copilot.router,      prefix="/copilot",            tags=["Copilot"])
app.include_router(reports.router,      prefix="/reports",            tags=["Reports"])
app.include_router(bhuvan.router,       prefix="/bhuvan",             tags=["Bhuvan/ISRO"])
app.include_router(alerts_router.router,prefix="/alerts",             tags=["Weather & Alerts"])
app.include_router(citizens_router.router, prefix="/citizens",        tags=["Citizen Intelligence"])


@app.get("/health", tags=["Meta"])
async def health():
    from app.simulation.disaster_state import state_ring_buffer
    latest = state_ring_buffer.get_latest()
    return JSONResponse({
        "status": "ok",
        "service": "route-resilience-amdiros",
        "version": "2.0.0",
        "loop": {
            "poll_interval_s": POLL_INTERVAL_S,
            "latest_seq": latest.sequence_no if latest else None,
            "latest_observed_at": latest.observed_at if latest else None,
        },
    })
