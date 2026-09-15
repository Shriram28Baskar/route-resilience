"""
/citizens — Citizen Intelligence API.

Citizen reports are an INDEPENDENT EVIDENCE LAYER.
They NEVER mutate flooded_node_ids, water_level_m, graph elevations,
or any physical simulation truth.

Agreement/disagreement with the digital twin is computed explicitly
and surfaced as a signal, not silently resolved.

Endpoints:
  POST   /citizens/report   — submit a distress report (full NLP → geo → evidence pipeline)
  GET    /citizens/reports  — list recent reports
  DELETE /citizens/reports  — clear all reports (demo reset)
"""
import logging
import uuid
import math
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from app.graph_pipeline.graph_build import GraphStore
from app.simulation.disaster_state import (
    CitizenEvidence, citizen_evidence_store, state_ring_buffer
)

logger = logging.getLogger(__name__)
router = APIRouter()

# ── NLP keyword sets ───────────────────────────────────────────────────────────
FLOOD_KEYWORDS = {
    "flood", "flooded", "flooding", "water", "submerged", "submerge",
    "inundated", "inundation", "overflow", "overflowing", "waterlogged",
    "blocked", "washed", "stuck", "stranded", "knee-deep", "waist-deep",
    "ankle", "puddle", "drain", "sewage", "entering", "rising",
}

# Max snap distance — reports further than this from any node are rejected
MAX_SNAP_DISTANCE_M = 500.0


class CitizenReportRequest(BaseModel):
    lat: float = Field(..., ge=12.0, le=14.0, description="Latitude (Bengaluru AOI)")
    lon: float = Field(..., ge=77.0, le=78.5, description="Longitude (Bengaluru AOI)")
    message: str = Field(..., min_length=5, max_length=500)
    severity: str = Field("high", pattern="^(critical|high|moderate|low)$")
    reporter_id: Optional[str] = Field(None, max_length=100)


def _npl_triage(message: str) -> bool:
    """Return True if message contains flooding-related language."""
    words = message.lower().split()
    return any(w.strip(".,!?;:'\"") in FLOOD_KEYWORDS for w in words)


def _haversine_m(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    R = 6_371_000.0
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = (math.sin(dlat / 2) ** 2
         + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2))
         * math.sin(dlon / 2) ** 2)
    return R * 2 * math.asin(math.sqrt(max(0.0, a)))


def _snap_to_nearest_node(G, lat: float, lon: float) -> Optional[tuple]:
    """
    Find nearest graph node to (lat, lon).
    Returns (node_id, distance_m) or None if no node within MAX_SNAP_DISTANCE_M.
    Does NOT mutate the graph.
    """
    best_node = None
    best_dist = float("inf")
    for node_id, data in G.nodes(data=True):
        nlat = data.get("y")
        nlon = data.get("x")
        if nlat is None or nlon is None:
            continue
        dist = _haversine_m(lat, lon, nlat, nlon)
        if dist < best_dist:
            best_dist = dist
            best_node = node_id
    if best_dist > MAX_SNAP_DISTANCE_M:
        return None
    return best_node, best_dist


def _compare_with_twin(
    snapped_node_id: Optional[int],
    flooding_indicator: bool,
    current_state,
) -> tuple[str, str]:
    """
    Compare citizen evidence against the current digital twin.

    Returns (twin_agreement, twin_note).
    twin_agreement: "AGREES" | "DISAGREES" | "UNVERIFIABLE"

    Citizen evidence NEVER mutates the twin. This function is read-only.
    """
    if snapped_node_id is None:
        return "UNVERIFIABLE", "Report location could not be snapped to road network."

    if current_state is None:
        return "UNVERIFIABLE", "No active digital twin state to compare against."

    flooded_count = current_state.flooded_node_count
    water_level = current_state.water_level_m

    # Check if the snapped node is in the flooded set
    # We access flooded node IDs from the ring buffer's latest state
    latest = state_ring_buffer.get_latest()
    if latest is None:
        return "UNVERIFIABLE", "No loop state in ring buffer yet."

    # Re-derive flooded set from the alive graph proxy
    # (We don't store full flooded_node_ids in DisasterState to keep it lean)
    # Use water_level against node elevation as a proxy
    try:
        G = GraphStore.get_osm_fallback()
        if G is None:
            return "UNVERIFIABLE", "Graph not loaded."
        node_data = G.nodes.get(snapped_node_id, {})
        node_elev = node_data.get("elevation")
        if node_elev is None:
            return "UNVERIFIABLE", "Node elevation not available."

        twin_says_flooded = node_elev <= water_level
        if flooding_indicator and twin_says_flooded:
            return "AGREES", (
                f"Twin also indicates this node (elevation {node_elev:.1f}m) "
                f"is below derived flood threshold ({water_level:.3f}m)."
            )
        elif flooding_indicator and not twin_says_flooded:
            return "DISAGREES", (
                f"Citizen reports flooding but twin shows node elevation {node_elev:.1f}m "
                f"is above derived flood threshold ({water_level:.3f}m). "
                "Possible causes: local drainage failure, infrastructure blockage, or DEM resolution limits."
            )
        elif not flooding_indicator and twin_says_flooded:
            return "UNVERIFIABLE", (
                f"Twin shows area below water ({water_level:.3f}m) but citizen report "
                "does not mention flooding."
            )
        else:
            return "AGREES", "No flooding reported; twin also shows area above water level."
    except Exception as exc:
        logger.warning(f"Twin comparison error: {exc}")
        return "UNVERIFIABLE", f"Comparison error: {exc}"


def _wake_citizen_loop() -> None:
    """Signal the existing scheduler; this helper never runs a cycle itself."""
    from app.main import get_citizen_trigger
    get_citizen_trigger().set()


# ── Endpoints ──────────────────────────────────────────────────────────────────

@router.post("/report")
async def submit_citizen_report(req: CitizenReportRequest):
    """
    Step 1 — NLP triage: detect flooding-related language.
    Step 2 — Geo-snap: find nearest graph node (read-only).
    Step 3 — Evidence comparison: check agreement with digital twin (read-only).
    Step 4 — Store in CitizenEvidenceStore (INDEPENDENT layer, never mutates graph).
    Step 5 — Flag for re-evaluation on next loop cycle.

    IMPORTANT: This endpoint NEVER modifies flooded_node_ids, water_level_m,
    graph node elevations, or any physical simulation state.
    """
    G = GraphStore.get_osm_fallback()
    if G is None:
        raise HTTPException(status_code=503, detail="Road graph not loaded yet.")

    # Step 1: NLP triage
    flooding_indicator = _npl_triage(req.message)

    # Step 2: Geo-snap (read-only)
    snap_result = _snap_to_nearest_node(G, req.lat, req.lon)
    if snap_result is None:
        raise HTTPException(
            status_code=422,
            detail={
                "error": "no_graph_node_nearby",
                "message": (
                    f"No road network node found within {MAX_SNAP_DISTANCE_M}m of "
                    f"({req.lat:.4f}, {req.lon:.4f}). "
                    "Report rejected — location outside Bengaluru road graph coverage."
                ),
            },
        )
    snapped_node_id, snap_distance_m = snap_result

    # Step 3: Compare with digital twin (read-only)
    current_state = state_ring_buffer.get_latest()
    twin_agreement, twin_note = _compare_with_twin(
        snapped_node_id, flooding_indicator, current_state
    )

    # Step 4: Build CitizenEvidence — does NOT touch graph
    evidence = CitizenEvidence(
        report_id=str(uuid.uuid4()),
        lat=req.lat,
        lon=req.lon,
        message=req.message,
        severity=req.severity,
        snapped_node_id=snapped_node_id,
        flooding_indicator=flooding_indicator,
        received_at=datetime.now(timezone.utc).isoformat(),
        twin_agreement=twin_agreement,
        twin_note=twin_note,
    )

    # Step 5: Store in the independent evidence layer, then wake the existing
    # serialised loop.  The endpoint never executes a cycle itself.
    citizen_evidence_store.add(evidence)
    _wake_citizen_loop()

    logger.info(
        f"Citizen report stored: node={snapped_node_id}, "
        f"flooding={flooding_indicator}, agreement={twin_agreement}, "
        f"snap_dist={snap_distance_m:.0f}m"
    )

    return JSONResponse({
        "status": "received",
        "report_id": evidence.report_id,
        "snapped_node_id": snapped_node_id,
        "snap_distance_m": round(snap_distance_m, 1),
        "flooding_indicator": flooding_indicator,
        "twin_agreement": twin_agreement,
        "twin_note": twin_note,
        "note": (
            "This report is stored as independent citizen evidence. "
            "It does NOT modify the physical flood simulation. "
            "It has queued the existing autonomous loop for immediate re-evaluation."
        ),
    })


@router.get("/reports")
async def list_citizen_reports(n: int = 50):
    """Return the most recent N citizen evidence reports."""
    reports = citizen_evidence_store.get_recent(min(n, 200))
    return JSONResponse({
        "count": len(reports),
        "reports": [
            {
                "report_id": r.report_id,
                "lat": r.lat,
                "lon": r.lon,
                "message": r.message,
                "severity": r.severity,
                "snapped_node_id": r.snapped_node_id,
                "flooding_indicator": r.flooding_indicator,
                "received_at": r.received_at,
                "twin_agreement": r.twin_agreement,
                "twin_note": r.twin_note,
            }
            for r in reversed(reports)  # newest first
        ],
    })


@router.delete("/reports")
async def clear_citizen_reports():
    """Clear all citizen evidence reports (demo reset)."""
    citizen_evidence_store.clear_all()
    logger.info("Citizen evidence store cleared.")
    return JSONResponse({"status": "cleared", "message": "All citizen reports cleared."})
