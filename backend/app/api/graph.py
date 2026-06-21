"""
/graph — road graph construction, healing, and analysis endpoints.

POST /graph/build      → skeletonize mask → raw NetworkX graph
POST /graph/heal       → apply MST healing to raw graph
GET  /graph/metrics    → connectivity statistics
GET  /graph/centrality → per-node betweenness centrality
"""
import io
import json
import base64
import logging
from typing import Optional

import numpy as np
from fastapi import APIRouter, HTTPException, Body, Response
from fastapi.responses import JSONResponse
from PIL import Image

from app.graph_pipeline.skeletonize import mask_to_skeleton
from app.graph_pipeline.graph_build import GraphStore, skeleton_to_graph, graph_to_geojson
from app.graph_pipeline.mst_healing import heal_graph
from app.graph_pipeline.centrality import compute_betweenness
from app.graph_pipeline.metrics import compute_graph_metrics

logger = logging.getLogger(__name__)
router = APIRouter()


@router.post("/build")
def build_graph(payload: dict = Body(...)):
    """
    Build a raw road graph from a base64-encoded binary mask.
    Body: { "mask_b64": "<base64 PNG>" }
    """
    mask_b64 = payload.get("mask_b64")
    if not mask_b64:
        raise HTTPException(status_code=400, detail="mask_b64 is required")

    try:
        mask_bytes = base64.b64decode(mask_b64)
        mask_img = Image.open(io.BytesIO(mask_bytes)).convert("L")
        mask = (np.array(mask_img) > 127).astype(np.uint8)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"Cannot decode mask: {exc}")

    skeleton = mask_to_skeleton(mask)
    G = skeleton_to_graph(skeleton)
    GraphStore.set_raw(G)

    geojson = graph_to_geojson(G)
    metrics = compute_graph_metrics(G)

    return JSONResponse({
        "graph_geojson": geojson,
        "metrics": metrics,
        "node_count": G.number_of_nodes(),
        "edge_count": G.number_of_edges(),
    })


@router.post("/heal")
def heal_road_graph():
    """
    Apply MST-based topological healing to the raw graph stored in GraphStore.
    Returns the healed graph GeoJSON plus a before/after comparison.
    """
    raw = GraphStore.get_raw()
    if raw is None:
        raise HTTPException(status_code=400, detail="No raw graph available. Call /graph/build first.")

    healed = heal_graph(raw)
    GraphStore.set_healed(healed)

    raw_metrics = compute_graph_metrics(raw)
    healed_metrics = compute_graph_metrics(healed)
    geojson = graph_to_geojson(healed)

    return JSONResponse({
        "graph_geojson": geojson,
        "before": raw_metrics,
        "after": healed_metrics,
        "connectivity_ratio": (
            healed_metrics["largest_component_size"] /
            max(raw_metrics["largest_component_size"], 1)
        ),
    })


@router.get("/metrics")
def graph_metrics(use_healed: bool = True):
    """
    Return connectivity statistics for the current graph.
    Query param use_healed=true (default) uses the healed graph.
    """
    G = GraphStore.get_healed() if use_healed else GraphStore.get_raw()
    if G is None:
        G = GraphStore.get_osm_fallback()
    if G is None:
        raise HTTPException(status_code=404, detail="No graph available.")

    return JSONResponse(compute_graph_metrics(G))


@router.get("/centrality")
def graph_centrality(top_n: Optional[int] = 20, k: Optional[int] = 50):
    """
    Compute betweenness centrality for all nodes.
    Returns full ranked list + top_n 'gatekeeper' nodes.
    """
    G = GraphStore.get_healed() or GraphStore.get_osm_fallback()
    if G is None:
        raise HTTPException(status_code=404, detail="No graph available.")

    centrality = compute_betweenness(G, k=k)
    ranked = sorted(centrality.items(), key=lambda x: x[1], reverse=True)
    gatekeepers = [
        {"node_id": str(nid), "score": score, **G.nodes[nid]}
        for nid, score in ranked[:top_n]
    ]
    all_scores = {str(nid): score for nid, score in centrality.items()}

    content = json.dumps({
        "gatekeepers": gatekeepers,
        "all_centrality": all_scores,
        "top_n": top_n,
    })
    return Response(content=content, media_type="application/json")


from app.graph_pipeline.centrality import compute_closeness, get_articulation_points, compute_edge_betweenness

@router.get("/criticality")
def graph_criticality(top_n: Optional[int] = 20, k: Optional[int] = 50):
    """
    Returns comprehensive criticality metrics: betweenness, closeness, articulation points, and edge betweenness.
    """
    G = GraphStore.get_healed() or GraphStore.get_osm_fallback()
    if G is None:
        raise HTTPException(status_code=404, detail="No graph available.")

    # For massive graphs (like the fallback), use a much smaller k to prevent timeouts
    n = G.number_of_nodes()
    effective_k = min(k, 5) if n > 5000 else k

    # 1. Betweenness
    betweenness = compute_betweenness(G, k=effective_k)
    ranked_b = sorted(betweenness.items(), key=lambda x: x[1], reverse=True)
    gatekeepers = [
        {"node_id": str(nid), "score": score, "x": G.nodes[nid].get("x", 0), "y": G.nodes[nid].get("y", 0)}
        for nid, score in ranked_b[:top_n]
    ]

    # 2. Closeness
    closeness = compute_closeness(G)

    # 3. Articulation Points
    aps = get_articulation_points(G)

    # 4. Edge Betweenness (Top edges only)
    edge_betw = compute_edge_betweenness(G, k=effective_k)
    # Sort and take top edges
    ranked_edges = sorted(edge_betw.items(), key=lambda x: x[1], reverse=True)[:50]
    critical_edges = [
        {"u": str(edge_key[0]), "v": str(edge_key[1]), "score": score}
        for edge_key, score in ranked_edges
    ]

    content = json.dumps({
        "betweenness": {str(nid): score for nid, score in betweenness.items()},
        "closeness": {str(nid): score for nid, score in closeness.items()},
        "gatekeepers": gatekeepers,
        "articulation_points": [str(nid) for nid in aps],
        "critical_edges": critical_edges
    })
    return Response(content=content, media_type="application/json")


@router.get("/geojson")
def graph_geojson():
    """
    Return the full GeoJSON FeatureCollection of the active road network.
    """
    G = GraphStore.get_healed() or GraphStore.get_osm_fallback()
    if G is None:
        raise HTTPException(status_code=404, detail="No graph available.")

    geojson = graph_to_geojson(G)
    content = json.dumps(geojson)
    return Response(content=content, media_type="application/json")
