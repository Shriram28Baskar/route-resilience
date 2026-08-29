"""
/accessibility — hospital and emergency service proximity analysis.

GET  /accessibility/hospitals      → nearest hospital distances per node, pre/post ablation
POST /accessibility/impact         → unified Emergency Accessibility Impact Engine
POST /accessibility/flood-impact   → Steps 4+5+6: multi-facility impact after flood
GET  /accessibility/equity         → equity analysis
GET  /accessibility/emergency-services → fire stations and police stations
"""
import json
import logging
import math
import os
import statistics
from typing import List, Optional, Dict

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from app.graph_pipeline.graph_build import GraphStore
from app.simulation.ablation import ablate_nodes
from app.integrations.overpass import fetch_facilities
from app.graph_pipeline.metrics import multi_source_shortest_paths
from app.simulation.equity import generate_equity_analysis
from app.simulation.resilience import compute_resilience_index
from app.simulation.routing import compute_route
from app.data.population import query_population_nodes

logger = logging.getLogger(__name__)
router = APIRouter()

# 15-minute emergency accessibility threshold in seconds
ACCESSIBILITY_CUTOFF_S = 900.0
# Degradation threshold: travel time increased by more than this fraction
DEGRADATION_THRESHOLD = 0.50

# BBMP ward boundaries path
WARDS_GEOJSON_PATH = os.environ.get(
    "WARDS_GEOJSON_PATH",
    r"C:\Users\Saish\OneDrive\Documents\route-resilience\DataSet\wards_bengaluru_gba.geojson"
)

# Ward boundaries cache: list of (ward_name, bbox, ring_coords)
_wards_cache = None
_wards_indexed = None  # list of (name, lat_min, lat_max, lon_min, lon_max, ring_coords)


def _load_wards():
    """
    Lazily load BBMP ward boundaries and build a bounding-box index for fast lookup.
    The GeoJSON stores coordinates as [lat, lon] (non-standard).
    """
    global _wards_cache, _wards_indexed
    if _wards_indexed is not None:
        return _wards_indexed
    if not os.path.exists(WARDS_GEOJSON_PATH):
        logger.warning(f"BBMP wards GeoJSON not found at {WARDS_GEOJSON_PATH}")
        _wards_indexed = []
        return _wards_indexed
    try:
        with open(WARDS_GEOJSON_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
        features = data.get("features", [])
        indexed = []
        for feat in features:
            geom = feat.get("geometry", {})
            props = feat.get("properties", {})
            name = props.get("ward_name") or props.get("WARD_NAME") or props.get("name") or "Unknown Ward"
            rings = []
            if geom.get("type") == "Polygon":
                rings = [geom["coordinates"][0]] if geom.get("coordinates") else []
            elif geom.get("type") == "MultiPolygon":
                rings = [poly[0] for poly in geom.get("coordinates", []) if poly]
            for ring in rings:
                if not ring:
                    continue
                lats = [c[0] for c in ring]
                lons = [c[1] for c in ring]
                indexed.append((name, min(lats), max(lats), min(lons), max(lons), ring))
        _wards_indexed = indexed
        logger.info(f"BBMP ward boundaries indexed: {len(features)} wards → {len(indexed)} rings")
    except Exception as e:
        logger.error(f"Failed to load BBMP wards: {e}")
        _wards_indexed = []
    return _wards_indexed


def _point_in_polygon(lat: float, lon: float, polygon_coords: list) -> bool:
    """
    Ray-casting algorithm.
    BBMP ward GeoJSON stores coordinates as [lat, lon] (non-standard).
    """
    tx, ty = lat, lon
    inside = False
    n = len(polygon_coords)
    j = n - 1
    for i in range(n):
        xi, yi = polygon_coords[i][0], polygon_coords[i][1]   # xi=lat, yi=lon
        xj, yj = polygon_coords[j][0], polygon_coords[j][1]
        if ((yi > ty) != (yj > ty)) and (tx < (xj - xi) * (ty - yi) / (yj - yi) + xi):
            inside = not inside
        j = i
    return inside


def _get_ward_for_node(lat: float, lon: float) -> Optional[str]:
    """
    Return BBMP ward name for (lat, lon) using a bbox pre-filter for speed.
    Average cost: O(1) polygon tests instead of O(369).
    """
    indexed = _load_wards()
    for name, lat_min, lat_max, lon_min, lon_max, ring in indexed:
        # Bounding-box pre-filter (reject ~99% of wards instantly)
        if lat < lat_min or lat > lat_max or lon < lon_min or lon > lon_max:
            continue
        if _point_in_polygon(lat, lon, ring):
            return name
    return None


def _get_affected_wards(G, node_ids: list) -> Dict[str, int]:
    """
    Return {ward_name: node_count} for flooded nodes.
    Source: BBMP ward boundaries GeoJSON.
    """
    ward_counts: Dict[str, int] = {}
    for n in node_ids:
        data = G.nodes.get(n, {})
        lat = data.get("y")
        lon = data.get("x")
        if lat is None or lon is None:
            continue
        ward = _get_ward_for_node(lat, lon) or "Outside Ward Boundary"

        ward_counts[ward] = ward_counts.get(ward, 0) + 1
    return ward_counts


# ── New request model ─────────────────────────────────────────────────────────

class FloodImpactRequest(BaseModel):
    """Request for multi-facility flood accessibility impact analysis."""
    ablated_node_ids: List[str]      # flooded node IDs from /simulate/flood
    south: float = 12.92
    west: float = 77.57
    north: float = 12.99
    east: float = 77.64


# ── Steps 4 + 5 + 6: Multi-facility flood impact endpoint ─────────────────────

@router.post("/flood-impact")
async def flood_accessibility_impact(req: FloodImpactRequest):
    """
    Steps 4, 5, 6: Multi-facility emergency accessibility impact after a flood.

    For each facility type (hospitals, fire stations, police stations):
      - Compute baseline travel time from every graph node (pre-flood)
      - Remove flooded nodes
      - Compute post-flood travel time
      - Report: nodes that lost 15-min access, avg travel time increase,
        disconnected facilities, best alternative route

    Also reports:
      - WorldPop population in the affected area (Step 5)
      - BBMP ward-level breakdown of flooded nodes (Step 8 preview)
      - Best alternative emergency route per facility type (Step 6)

    All numbers are derived from graph computations and real datasets.
    No estimates are fabricated.
    """
    G = GraphStore.get_healed() or GraphStore.get_osm_fallback()
    if G is None:
        raise HTTPException(status_code=404, detail="No graph available.")

    # Validate ablated node IDs
    node_map = {str(n): n for n in G.nodes()}
    flooded_nodes = [node_map[nid] for nid in req.ablated_node_ids if nid in node_map]
    invalid_count = len(req.ablated_node_ids) - len(flooded_nodes)
    if invalid_count:
        logger.warning(f"flood-impact: {invalid_count} node IDs not in graph (ignored)")

    if not flooded_nodes:
        raise HTTPException(status_code=400, detail="No valid flooded node IDs found in graph.")

    # Build post-flood subgraph (remove flooded nodes)
    perturbed = ablate_nodes(G, flooded_nodes)

    # ── Facility types to analyse ────────────────────────────────────────────
    FACILITY_TYPES = [
        {
            "key": "hospitals",
            "label": "Hospitals & Clinics",
            "amenities": ["hospital", "clinic", "health_post"],
        },
        {
            "key": "fire_stations",
            "label": "Fire Stations",
            "amenities": ["fire_station"],
        },
        {
            "key": "police",
            "label": "Police Stations",
            "amenities": ["police"],
        },
    ]

    facility_results = {}

    for ftype in FACILITY_TYPES:
        key = ftype["key"]
        logger.info(f"flood-impact: analysing {key}...")

        # Fetch POIs from Overpass (cached after first call)
        pois = await fetch_facilities(
            south=req.south, west=req.west, north=req.north, east=req.east,
            amenities=ftype["amenities"],
        )
        if not pois:
            facility_results[key] = {
                "label": ftype["label"],
                "facility_count": 0,
                "error": "No facilities found via Overpass API",
            }
            continue

        # Snap POI coordinates to nearest graph nodes
        fac_nodes = _snap_to_graph(G, pois)
        flooded_set = set(flooded_nodes)
        facilities_flooded = [n for n in fac_nodes if n in flooded_set]
        facilities_intact = [n for n in fac_nodes if n not in flooded_set]

        # Baseline accessibility (pre-flood)
        baseline_cov = _compute_time_coverage(G, fac_nodes)
        baseline_accessible = {nid: t for nid, t in baseline_cov.items() if t <= ACCESSIBILITY_CUTOFF_S}
        baseline_avg = statistics.mean(baseline_accessible.values()) if baseline_accessible else None

        # Post-flood accessibility
        perturbed_cov = _compute_time_coverage(perturbed, fac_nodes)
        perturbed_accessible = {nid: t for nid, t in perturbed_cov.items() if t <= ACCESSIBILITY_CUTOFF_S}
        perturbed_avg = statistics.mean(perturbed_accessible.values()) if perturbed_accessible else None

        # Delta: which nodes lost 15-min access?
        nodes_lost = []
        nodes_degraded = []
        time_increases = []

        for nid, base_t in baseline_accessible.items():
            if nid in req.ablated_node_ids:
                continue  # node itself is flooded — skip
            if nid not in perturbed_cov:
                nodes_lost.append(nid)
                time_increases.append(3600.0)  # 1hr penalty for total disconnection
                continue
            post_t = perturbed_cov[nid]
            if post_t > ACCESSIBILITY_CUTOFF_S:
                nodes_lost.append(nid)
                time_increases.append(post_t - base_t)
            elif post_t > base_t * (1 + DEGRADATION_THRESHOLD):
                nodes_degraded.append(nid)
                time_increases.append(post_t - base_t)

        avg_increase = statistics.mean(time_increases) if time_increases else 0.0
        median_increase = statistics.median(time_increases) if time_increases else 0.0

        # Disconnected facility count
        disconnected = _count_disconnected_hospitals(perturbed, fac_nodes)

        # Best alternative route (Step 6):
        # Prioritise nodes_degraded (still connected, just slower) over nodes_lost
        # (which may be fully isolated). Scan up to 20 candidates to find a routable pair.
        alt_route = None
        if facilities_intact:
            # candidates: degraded nodes first (most likely still connected), then lost nodes
            route_candidates = nodes_degraded + nodes_lost
            for candidate in route_candidates[:20]:
                src = node_map.get(candidate)
                if src is None or src not in perturbed:
                    continue
                nearest_fac = _nearest_reachable_hospital(perturbed, src, facilities_intact)
                if nearest_fac is None:
                    continue
                route = compute_route(perturbed, src, nearest_fac, weight_type="time_s", num_alternatives=0)
                if route.get("reachable"):
                    alt_route = {
                        "from_node": candidate,
                        "to_facility_node": str(nearest_fac),
                        "distance_m": route.get("distance_m"),
                        "travel_time_s": route.get("travel_time_s"),
                        "travel_time_min": round((route.get("travel_time_s") or 0) / 60, 1),
                        "path_nodes": route.get("path_nodes", []),
                        "path_geojson": route.get("path_geojson"),
                    }
                    break

        facility_results[key] = {
            "label": ftype["label"],
            "facility_count": len(pois),
            "facility_nodes_total": len(fac_nodes),
            "facilities_flooded": len(facilities_flooded),
            "facilities_intact": len(facilities_intact),
            "baseline": {
                "accessible_nodes": len(baseline_accessible),
                "avg_travel_time_s": round(baseline_avg, 1) if baseline_avg else None,
                "avg_travel_time_min": round(baseline_avg / 60, 1) if baseline_avg else None,
            },
            "post_flood": {
                "accessible_nodes": len(perturbed_accessible),
                "avg_travel_time_s": round(perturbed_avg, 1) if perturbed_avg else None,
                "avg_travel_time_min": round(perturbed_avg / 60, 1) if perturbed_avg else None,
            },
            "impact": {
                "nodes_lost_15min_access": len(nodes_lost),
                "nodes_degraded": len(nodes_degraded),
                "avg_travel_time_increase_s": round(avg_increase, 1),
                "avg_travel_time_increase_min": round(avg_increase / 60, 1),
                "median_travel_time_increase_s": round(median_increase, 1),
                "facilities_disconnected": disconnected,
            },
            "best_alternative_route": alt_route,
        }

    # ── Step 5: Population in flooded area (WorldPop) ─────────────────────────
    pop_result = query_population_nodes(G, flooded_nodes)

    # ── Step 8 preview: Ward-level breakdown ──────────────────────────────────
    logger.info("flood-impact: computing ward breakdown...")
    ward_breakdown = _get_affected_wards(G, flooded_nodes)

    # Sort wards by node count descending
    top_wards = sorted(ward_breakdown.items(), key=lambda x: x[1], reverse=True)[:15]

    # ── Road length affected ──────────────────────────────────────────────────
    flooded_set = set(flooded_nodes)
    road_length_m = sum(
        data.get("length", 0)
        for u, v, data in G.edges(data=True)
        if u in flooded_set or v in flooded_set
    )

    result = {
        "flood_summary": {
            "flooded_nodes": len(flooded_nodes),
            "total_nodes": G.number_of_nodes(),
            "flood_fraction": round(len(flooded_nodes) / G.number_of_nodes(), 4),
            "road_length_flooded_m": round(road_length_m, 1),
            "road_length_flooded_km": round(road_length_m / 1000, 2),
        },
        "population": {
            "affected": pop_result.get("population"),
            "source": pop_result.get("source"),
            "estimation_method": "WorldPop_2020_bounding_box_of_flooded_nodes",
        },
        "ward_breakdown": {
            "top_affected_wards": [{"ward": w, "flooded_nodes": c} for w, c in top_wards],
            "total_wards_affected": len(ward_breakdown),
            "source": "BBMP_ward_boundaries_GeoJSON",
        },
        "facility_impact": facility_results,
        "data_sources": {
            "graph": "OpenStreetMap via OSMnx",
            "facilities": "Overpass API (real-time OSM)",
            "population": "WorldPop_2020_UNadj_constrained_100m",
            "ward_boundaries": "BBMP_GeoJSON",
            "flood_nodes": "SRTMGL1_30m_static_approximation",
        },
    }

    logger.info(
        f"flood-impact complete: {len(flooded_nodes)} flooded nodes, "
        f"pop={pop_result.get('population')}, wards={len(ward_breakdown)}"
    )
    return JSONResponse(result)


class HospitalRequest(BaseModel):
    ablated_node_ids: Optional[List[str]] = []


class ImpactRequest(BaseModel):
    ablated_node_ids: List[str]
    south: float = 12.92
    west: float = 77.57
    north: float = 12.99
    east: float = 77.64


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


@router.post("/impact")
async def accessibility_impact(req: ImpactRequest):
    """
    Emergency Accessibility Impact Engine.

    Computes the full pipeline:
        hospitals → snap → baseline 15-min coverage →
        ablate → post-disaster coverage → delta →
        quantified impact → best alternative route →
        store result for copilot context

    All numbers are derived from actual graph computations.
    No population estimates are reported.
    """
    G = GraphStore.get_healed() or GraphStore.get_osm_fallback()
    if G is None:
        raise HTTPException(status_code=404, detail="No graph available.")

    # ── 1. Fetch and snap hospital POIs ─────────────────────────────────────
    hospitals = await fetch_facilities(
        south=req.south, west=req.west, north=req.north, east=req.east,
        amenities=["hospital", "clinic", "health_post"],
    )
    if not hospitals:
        raise HTTPException(
            status_code=404,
            detail="No hospitals found in the AOI via Overpass. Cannot compute accessibility impact."
        )

    hospital_nodes = _snap_to_graph(G, hospitals)
    logger.info(f"Impact engine: {len(hospitals)} hospitals → {len(hospital_nodes)} unique graph nodes")

    # ── 2. Validate ablated nodes ─────────────────────────────────────────
    node_map = {str(n): n for n in G.nodes()}
    target_nodes = [node_map[nid] for nid in req.ablated_node_ids if nid in node_map]
    invalid = [nid for nid in req.ablated_node_ids if nid not in node_map]
    if invalid:
        logger.warning(f"Impact engine: {len(invalid)} unknown node IDs ignored: {invalid[:5]}")

    if not target_nodes:
        raise HTTPException(
            status_code=400,
            detail="None of the provided node IDs exist in the graph."
        )

    # ── 3. Baseline 15-min accessibility (time_s weight) ─────────────────
    baseline_coverage = _compute_time_coverage(G, hospital_nodes)
    baseline_accessible = {
        nid: t for nid, t in baseline_coverage.items()
        if t <= ACCESSIBILITY_CUTOFF_S
    }
    baseline_inaccessible = {
        nid: t for nid, t in baseline_coverage.items()
        if t > ACCESSIBILITY_CUTOFF_S
    }
    baseline_times = list(baseline_accessible.values())
    baseline_avg = statistics.mean(baseline_times) if baseline_times else None

    # ── 4. Apply failure and compute post-disaster accessibility ──────────
    perturbed = ablate_nodes(G, target_nodes)
    perturbed_coverage = _compute_time_coverage(perturbed, hospital_nodes)
    perturbed_accessible = {
        nid: t for nid, t in perturbed_coverage.items()
        if t <= ACCESSIBILITY_CUTOFF_S
    }
    perturbed_times = list(perturbed_accessible.values())
    perturbed_avg = statistics.mean(perturbed_times) if perturbed_times else None

    # ── 5. Compute delta ──────────────────────────────────────────────────
    nodes_lost_access = []
    nodes_degraded = []
    time_increases = []

    for nid, baseline_t in baseline_accessible.items():
        if nid not in perturbed_coverage:
            # If the node was explicitly ablated, skip it (it's destroyed, not just cut off)
            if nid in req.ablated_node_ids:
                continue
            # Otherwise, the node still exists but is completely unreachable from any hospital
            # (i.e. it is in an isolated component with no hospitals)
            nodes_lost_access.append(nid)
            time_increases.append(3600.0) # Assume 1hr penalty for total disconnection
            continue

        post_t = perturbed_coverage[nid]
        if post_t > ACCESSIBILITY_CUTOFF_S:
            nodes_lost_access.append(nid)
            time_increases.append(post_t - baseline_t)
        elif post_t > baseline_t * (1 + DEGRADATION_THRESHOLD):
            nodes_degraded.append(nid)
            time_increases.append(post_t - baseline_t)

    avg_time_increase = statistics.mean(time_increases) if time_increases else 0.0
    median_time_increase = statistics.median(time_increases) if time_increases else 0.0

    # ── 6. Count disconnected hospitals ──────────────────────────────────
    # A hospital is "disconnected" if no node in perturbed graph can reach it
    disconnected_hospital_count = _count_disconnected_hospitals(perturbed, hospital_nodes)

    # ── 7. Resilience index change ────────────────────────────────────────
    ri_result = compute_resilience_index(G, perturbed, sample_size=60)

    # ── 8. Best alternative route from worst-affected area ───────────────
    best_alt_route = None
    if nodes_lost_access and hospital_nodes:
        # Find the "centroid" node (most central lost-access node by graph index)
        # Pick the first lost-access node that still exists in perturbed graph
        candidate_sources = [nid for nid in nodes_lost_access if nid not in req.ablated_node_ids]
        if candidate_sources and len(candidate_sources) > 0:
            source_nid = candidate_sources[len(candidate_sources) // 2]  # pick median
            source_node = node_map.get(source_nid)
            # Find nearest reachable hospital in perturbed graph
            best_hospital_node = _nearest_reachable_hospital(perturbed, source_node, hospital_nodes)
            if source_node and best_hospital_node:
                route = compute_route(perturbed, source_node, best_hospital_node, weight_type="time_s", num_alternatives=1)
                if route.get("reachable"):
                    best_alt_route = route

    # ── 9. Build and store result ─────────────────────────────────────────
    result = {
        "hospital_count": len(hospitals),
        "hospital_node_ids": [str(n) for n in hospital_nodes],
        "hospitals": hospitals,
        "ablated_node_ids": req.ablated_node_ids,
        "baseline": {
            "accessible_node_count": len(baseline_accessible),
            "inaccessible_node_count": len(baseline_inaccessible),
            "avg_time_s": round(baseline_avg, 1) if baseline_avg else None,
            "node_coverage": {nid: round(t, 1) for nid, t in baseline_coverage.items()},
        },
        "post_disaster": {
            "accessible_node_count": len(perturbed_accessible),
            "inaccessible_node_count": len(G.nodes()) - len(perturbed_accessible) - len(target_nodes),
            "avg_time_s": round(perturbed_avg, 1) if perturbed_avg else None,
            "node_coverage": {nid: round(t, 1) for nid, t in perturbed_coverage.items()},
        },
        "impact": {
            "nodes_lost_access": nodes_lost_access,
            "nodes_lost_access_count": len(nodes_lost_access),
            "nodes_degraded": nodes_degraded,
            "nodes_degraded_count": len(nodes_degraded),
            "avg_travel_time_increase_s": round(avg_time_increase, 1),
            "median_travel_time_increase_s": round(median_time_increase, 1),
            "disconnected_hospital_count": disconnected_hospital_count,
            "resilience_index_before": ri_result.get("baseline_avg_path"),
            "resilience_index_after": ri_result.get("perturbed_avg_path"),
            "resilience_index": ri_result.get("resilience_index"),
            "network_disconnected": ri_result.get("disconnected", False),
            "partition_count": ri_result.get("partition_count", 1),
        },
        "best_alternative_route": best_alt_route,
    }

    # Persist for copilot context
    GraphStore.set_last_accessibility_impact(_summarise_for_copilot(result))
    logger.info(
        f"Impact engine complete: {len(nodes_lost_access)} nodes lost access, "
        f"{len(nodes_degraded)} degraded, "
        f"{disconnected_hospital_count} hospitals disconnected"
    )

    return JSONResponse(result)


# ── Helper functions ──────────────────────────────────────────────────────────

def _compute_time_coverage(G, hospital_nodes: list) -> dict:
    """
    Multi-source Dijkstra using time_s weight.
    Returns {node_id_str: travel_time_s} for all reachable nodes.
    """
    import networkx as nx
    valid_sources = [s for s in hospital_nodes if s in G]
    if not valid_sources:
        return {}
    try:
        distances, _ = nx.multi_source_dijkstra(G, valid_sources, weight="time_s")
        return {str(node): dist for node, dist in distances.items()}
    except Exception as exc:
        logger.warning(f"Time-based multi-source Dijkstra failed: {exc}")
        return {}


def _count_disconnected_hospitals(G, hospital_nodes: list) -> int:
    """
    Count hospitals whose graph node has been removed or is in an isolated component.
    A hospital is disconnected if it has degree 0 or is not in G at all.
    """
    import networkx as nx
    count = 0
    if G.number_of_nodes() == 0:
        return len(hospital_nodes)
    # Use LCC membership
    try:
        components = list(nx.connected_components(G))
        lcc = max(components, key=len) if components else set()
    except Exception:
        lcc = set(G.nodes())
    for hn in hospital_nodes:
        if hn not in G or hn not in lcc:
            count += 1
    return count


def _nearest_reachable_hospital(G, source_node, hospital_nodes: list):
    """
    Return the hospital node with shortest path to source_node in perturbed graph.
    """
    import networkx as nx
    if source_node is None or source_node not in G:
        return None
    best_node = None
    best_dist = float("inf")
    for hn in hospital_nodes:
        if hn not in G:
            continue
        try:
            d = nx.dijkstra_path_length(G, source_node, hn, weight="time_s")
            if d < best_dist:
                best_dist = d
                best_node = hn
        except (nx.NetworkXNoPath, nx.NodeNotFound):
            continue
    return best_node


def _snap_to_graph(G, hospitals: list) -> list:
    """Snap hospital (lat, lon) points to the nearest graph node."""
    nodes = [(n, data) for n, data in G.nodes(data=True) if "x" in data and "y" in data]
    snapped = []
    for h in hospitals:
        hlat, hlon = h["lat"], h["lon"]
        best = min(nodes, key=lambda nd: math.hypot(nd[1]["x"] - hlon, nd[1]["y"] - hlat))
        snapped.append(best[0])
    return list(set(snapped))  # deduplicate


def _summarise_for_copilot(result: dict) -> dict:
    """
    Build a compact summary of the impact result for the copilot context.
    Excludes large node lists to stay within token budget.
    """
    impact = result.get("impact", {})
    baseline = result.get("baseline", {})
    post = result.get("post_disaster", {})
    alt_route = result.get("best_alternative_route")

    return {
        "analysis_type": "emergency_accessibility_impact",
        "hospitals_in_aoi": result.get("hospital_count", 0),
        "hospital_names": [h.get("name", "Unknown") for h in result.get("hospitals", [])],
        "ablated_nodes": result.get("ablated_node_ids", []),
        "baseline_accessible_nodes": baseline.get("accessible_node_count"),
        "baseline_avg_travel_time_s": baseline.get("avg_time_s"),
        "post_disaster_accessible_nodes": post.get("accessible_node_count"),
        "post_disaster_avg_travel_time_s": post.get("avg_time_s"),
        "nodes_lost_15min_access": impact.get("nodes_lost_access_count"),
        "nodes_with_degraded_access": impact.get("nodes_degraded_count"),
        "avg_travel_time_increase_s": impact.get("avg_travel_time_increase_s"),
        "median_travel_time_increase_s": impact.get("median_travel_time_increase_s"),
        "hospitals_disconnected": impact.get("disconnected_hospital_count"),
        "network_disconnected": impact.get("network_disconnected"),
        "partition_count": impact.get("partition_count"),
        "resilience_index": impact.get("resilience_index"),
        "alternative_route_available": alt_route is not None and alt_route.get("reachable", False),
        "alternative_route_travel_time_s": alt_route.get("travel_time_s") if alt_route else None,
        "alternative_route_distance_m": alt_route.get("distance_m") if alt_route else None,
    }


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


# ── Step 8: Ward-level report ─────────────────────────────────────────────────

class WardReportRequest(BaseModel):
    """Request for ward-level flood impact report."""
    ablated_node_ids: List[str]   # flooded node IDs from /simulate/flood
    south: float = 12.92
    west: float = 77.57
    north: float = 12.99
    east: float = 77.64


@router.post("/ward-report")
async def ward_report(req: WardReportRequest):
    """
    Step 8: Ward-level flood impact report.

    For each BBMP ward affected by the flood, reports:
      - ward_name: official BBMP name
      - census_population: from BBMP GeoJSON TOT_P field (2011 Census)
      - flooded_nodes: number of OSM graph nodes inside this ward that are flooded
      - total_nodes: total OSM nodes in this ward (baseline)
      - flood_fraction_pct: flooded_nodes / total_nodes × 100
      - assembly_constituency: from BBMP GeoJSON 'Assembly' field
      - zone: from BBMP GeoJSON 'zone_name' field

    Data sources:
      - Ward boundaries + census: BBMP GeoJSON (ward_name, TOT_P, Assembly, zone_name)
      - Flooded nodes: SRTMGL1 30m DEM via /simulate/flood
      - Graph: OpenStreetMap via OSMnx

    All population figures are 2011 census values from BBMP GeoJSON,
    clearly labelled. No estimation applied.
    """
    G = GraphStore.get_healed() or GraphStore.get_osm_fallback()
    if G is None:
        raise HTTPException(status_code=404, detail="No graph available.")

    node_map = {str(n): n for n in G.nodes()}
    flooded_nodes = [node_map[nid] for nid in req.ablated_node_ids if nid in node_map]
    if not flooded_nodes:
        raise HTTPException(status_code=400, detail="No valid flooded node IDs.")

    flooded_set = set(flooded_nodes)

    # Load ward index (triggers lazy load + bbox indexing)
    _load_wards()

    # Load raw features for census data (ward name → census properties)
    import json
    ward_props = {}  # ward_name -> properties dict
    try:
        with open(WARDS_GEOJSON_PATH, "r", encoding="utf-8") as f:
            raw = json.load(f)
        for feat in raw.get("features", []):
            props = feat.get("properties", {})
            name = props.get("ward_name") or props.get("WARD_NAME") or "Unknown Ward"
            ward_props[name] = props
    except Exception as e:
        logger.warning(f"Could not load BBMP census props: {e}")

    # Count all graph nodes per ward (baseline)
    ward_total: Dict[str, int] = {}
    ward_flooded: Dict[str, int] = {}

    for node, data in G.nodes(data=True):
        lat = data.get("y")
        lon = data.get("x")
        if lat is None or lon is None:
            continue
        ward = _get_ward_for_node(lat, lon)
        if ward is None:
            continue
        ward_total[ward] = ward_total.get(ward, 0) + 1
        if node in flooded_set:
            ward_flooded[ward] = ward_flooded.get(ward, 0) + 1

    # Build per-ward report
    ward_reports = []
    for ward_name, total in ward_total.items():
        flooded_count = ward_flooded.get(ward_name, 0)
        props = ward_props.get(ward_name, {})
        census_pop = int(float(props.get("TOT_P", 0) or 0))
        flood_frac = round(flooded_count / total * 100, 1) if total > 0 else 0.0

        ward_reports.append({
            "ward_name": ward_name,
            "ward_id": props.get("ward_id", ""),
            "assembly_constituency": props.get("Assembly", ""),
            "zone": props.get("zone_name", ""),
            "census_population_2011": census_pop,
            "population_source": "BBMP_GeoJSON_2011_Census",
            "graph_nodes_total": total,
            "graph_nodes_flooded": flooded_count,
            "flood_fraction_pct": flood_frac,
            "severity": (
                "critical" if flood_frac >= 60
                else "high" if flood_frac >= 30
                else "moderate" if flood_frac >= 10
                else "low"
            ),
        })

    # Sort by flood fraction descending
    ward_reports.sort(key=lambda w: w["flood_fraction_pct"], reverse=True)
    affected = [w for w in ward_reports if w["graph_nodes_flooded"] > 0]

    # Aggregate stats
    total_census_pop = sum(w["census_population_2011"] for w in affected)
    critical_wards = [w["ward_name"] for w in affected if w["severity"] == "critical"]
    high_wards = [w["ward_name"] for w in affected if w["severity"] == "high"]

    return JSONResponse({
        "summary": {
            "total_wards_in_graph": len(ward_total),
            "wards_affected": len(affected),
            "wards_critical": len(critical_wards),
            "wards_high": len(high_wards),
            "total_census_pop_in_affected_wards": total_census_pop,
            "population_source": "BBMP_GeoJSON_2011_Census",
            "population_note": "2011 Census ward totals — not a current estimate",
        },
        "critical_wards": critical_wards,
        "high_impact_wards": high_wards,
        "ward_reports": affected,
        "data_sources": {
            "ward_boundaries": "BBMP_ward_boundaries_GeoJSON",
            "census_population": "BBMP_GeoJSON_TOT_P_2011_Census",
            "flood_nodes": "SRTMGL1_30m_static_approximation",
            "graph": "OpenStreetMap_via_OSMnx",
        },
    })
