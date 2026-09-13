"""
Route Resilience — FastAPI backend entrypoint.
Mounts all sub-routers and configures CORS, lifespan, and logging.
"""
import logging
from contextlib import asynccontextmanager

from dotenv import load_dotenv
load_dotenv()  # Load environment variables from .env before imports

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.api import segmentation, graph, simulation, accessibility, copilot, reports, bhuvan, alerts as alerts_router, historical, temporal
from app.graph_pipeline.graph_build import GraphStore

logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)s | %(name)s | %(message)s")
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup / shutdown lifecycle hook."""
    logger.info("🚀 Route Resilience backend starting up …")
    # Pre-warm graph store (loads OSM fallback if available)
    await GraphStore.initialize()

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
            from app.simulation.recommendations import generate_recommendations
            from app.api.simulation import _RECOMMENDATIONS_CACHE
            _RECOMMENDATIONS_CACHE["data"] = generate_recommendations(G)
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

    yield
    logger.info("👋 Route Resilience backend shutting down …")


app = FastAPI(
    title="Route Resilience API",
    description="Occlusion-robust road extraction, graph analysis, and disaster simulation.",
    version="1.0.0",
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
app.include_router(segmentation.router, prefix="/segment",           tags=["Segmentation"])
app.include_router(graph.router,        prefix="/graph",              tags=["Graph"])
app.include_router(simulation.router,   prefix="/simulate",           tags=["Simulation"])
app.include_router(historical.router,   prefix="/simulate/historical",tags=["Historical Scenarios"])
app.include_router(temporal.router,     prefix="/simulate",           tags=["Temporal Projection"])
app.include_router(accessibility.router,prefix="/accessibility",      tags=["Accessibility"])
app.include_router(copilot.router,      prefix="/copilot",            tags=["Copilot"])
app.include_router(reports.router,      prefix="/reports",            tags=["Reports"])
app.include_router(bhuvan.router,       prefix="/bhuvan",             tags=["Bhuvan/ISRO"])
app.include_router(alerts_router.router,prefix="/alerts",             tags=["Weather & Alerts"])


@app.get("/health", tags=["Meta"])
async def health():
    return JSONResponse({"status": "ok", "service": "route-resilience-api"})
