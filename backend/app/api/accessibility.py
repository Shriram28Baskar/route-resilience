"""
/accessibility — hospital and emergency service proximity analysis.

GET /accessibility/hospitals → nearest hospital distances per node, pre/post ablation
"""
import logging
from typing import List, Optional

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from app.graph_pipeline.graph_build import GraphStore
from app.simulation.ablation import ablate_nodes
from app.integrations.overpass import fetch_facilities
from app.graph_pipeline.metrics import multi_source_shortest_paths
from app.simulation.equity import generate_equity_analysis

logger = logging.getLogger(__name__)
router = APIRouter()


class HospitalRequest(BaseModel):
    ablated_node_ids: Optional[List[str]] = []


@router.get("/hospitals")
async def hospital_accessibility(
    south: float = Query(12.92),
    west: float = Query(77.57),
    north: float = Query(12.99),
    east: float = Query(77.64),
    ablated_node_ids: Optional[str] = Query(None, description="Comma-separated node IDs to ablate"),
):
    """
    Fetch hospital POIs from OSM for the given bounding box, snap them to
    graph nodes, then compute shortest path distance from every node to its
    nearest hospital — both baseline and post-ablation.
    """
    G = GraphStore.get_healed() or GraphStore.get_osm_fallback()
    if G is None:
        raise HTTPException(status_code=404, detail="No graph available.")

    # Fetch or use cached facilities (hospitals only for this endpoint for backward compatibility)
    hospitals = await fetch_facilities(south=south, west=west, north=north, east=east, amenities=["hospital", "clinic", "health_post"])
    if not hospitals:
        raise HTTPException(status_code=404, detail="No hospitals found in the given bounding box.")

    # Snap hospital coordinates to nearest graph nodes
    hospital_nodes = _snap_to_graph(G, hospitals)

    # Baseline distances
    baseline_dist = multi_source_shortest_paths(G, hospital_nodes)

    result: dict = {
        "hospitals": hospitals,
        "hospital_node_ids": [str(n) for n in hospital_nodes],
        "baseline": {str(k): v for k, v in baseline_dist.items()},
        "perturbed": None,
        "unreachable_delta": None,
    }

    if ablated_node_ids:
        node_map = {str(n): n for n in G.nodes()}
        ids = [node_map[nid] for nid in ablated_node_ids.split(",") if nid.strip() in node_map]
        perturbed = ablate_nodes(G, ids)
        perturbed_dist = multi_source_shortest_paths(perturbed, hospital_nodes)

        # Nodes that lose hospital access entirely
        unreachable = [
            str(n) for n in G.nodes()
            if str(n) in result["baseline"] and str(n) not in {str(k): k for k in perturbed_dist}
        ]

        result["perturbed"] = {str(k): v for k, v in perturbed_dist.items()}
        result["unreachable_delta"] = unreachable

    return JSONResponse(result)


def _snap_to_graph(G, hospitals: list) -> list:
    """Snap hospital (lat, lon) points to the nearest graph node."""
    import math

    nodes = [(n, data) for n, data in G.nodes(data=True) if "x" in data and "y" in data]
    snapped = []

    for h in hospitals:
        hlat, hlon = h["lat"], h["lon"]
        best = min(nodes, key=lambda nd: math.hypot(nd[1]["x"] - hlon, nd[1]["y"] - hlat))
        snapped.append(best[0])

    return list(set(snapped))  # deduplicate

@router.get("/equity")
async def equity_analysis(
    south: float = Query(12.92),
    west: float = Query(77.57),
    north: float = Query(12.99),
    east: float = Query(77.64),
):
    """
    Generate equity analysis (healthcare deserts, vulnerable populations).
    """
    G = GraphStore.get_healed() or GraphStore.get_osm_fallback()
    if G is None:
        raise HTTPException(status_code=404, detail="No graph available.")
        
    facilities = await fetch_facilities(south=south, west=west, north=north, east=east)
    if not facilities:
        raise HTTPException(status_code=404, detail="No facilities found.")
        
    result = generate_equity_analysis(G, facilities)
    return JSONResponse(result)

@router.get("/emergency-services")
async def emergency_services(
    south: float = Query(12.92),
    west: float = Query(77.57),
    north: float = Query(12.99),
    east: float = Query(77.64),
):
    """
    Fetch fire stations and police stations from OSM for the given bounding box.
    """
    G = GraphStore.get_healed() or GraphStore.get_osm_fallback()
    if G is None:
        raise HTTPException(status_code=404, detail="No graph available.")

    facilities = await fetch_facilities(south=south, west=west, north=north, east=east, amenities=["fire_station", "police"])
    
    # Snap to graph
    snapped_nodes = _snap_to_graph(G, facilities)

    return {
        "facilities": facilities,
        "facility_node_ids": [str(n) for n in snapped_nodes]
    }
