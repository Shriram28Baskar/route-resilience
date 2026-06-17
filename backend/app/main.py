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

from app.api import segmentation, graph, simulation, accessibility, copilot, reports
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
        G = GraphStore.get_osm_fallback()
        if G is not None:
            logger.info("Warmup: Starting background OSM graph metrics precompute ...")
            compute_graph_metrics(G)
            
            from app.graph_pipeline.centrality import compute_closeness, get_articulation_points, compute_edge_betweenness
            
            logger.info("Warmup: Starting background OSM betweenness centrality (k=50) precompute ...")
            compute_betweenness(G, k=50)
            
            logger.info("Warmup: Starting background OSM closeness centrality precompute ...")
            compute_closeness(G)
            
            logger.info("Warmup: Starting background OSM articulation points precompute ...")
            get_articulation_points(G)
            
            logger.info("Warmup: Starting background OSM edge betweenness (k=50) precompute ...")
            compute_edge_betweenness(G, k=50)
            
            logger.info("Warmup: Background pre-computation complete!")

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
    allow_origins=["http://localhost:3000", "http://127.0.0.1:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Routers ───────────────────────────────────────────────────────────────────
app.include_router(segmentation.router, prefix="/segment",    tags=["Segmentation"])
app.include_router(graph.router,        prefix="/graph",       tags=["Graph"])
app.include_router(simulation.router,   prefix="/simulate",    tags=["Simulation"])
app.include_router(accessibility.router,prefix="/accessibility",tags=["Accessibility"])
app.include_router(copilot.router,      prefix="/copilot",     tags=["Copilot"])
app.include_router(reports.router,      prefix="/reports",     tags=["Reports"])


@app.get("/health", tags=["Meta"])
async def health():
    return JSONResponse({"status": "ok", "service": "route-resilience-api"})
