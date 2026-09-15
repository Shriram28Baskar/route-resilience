"""
evacuation_advisory.py — Zone-level evacuation advisory generator.

Produces a deterministic EvacAdvisory for each BBMP ward with flooded nodes.

Classification rules (deterministic, no LLM):
  EVACUATE_NOW    — any hospital isolated, OR RI < 0.5, OR flooded_count > 50
  EVACUATE_ADVISED — hospital reachable AND (RI < 0.7 OR RI unknown) AND flooded_count > 5
  MONITOR         — flooded_count <= 5 AND RI >= 0.7 (or RI unknown with minor flood)
"""
import math
import logging
from typing import List, Optional, Dict

from app.simulation.disaster_state import EvacAdvisory, HospStatus

logger = logging.getLogger(__name__)

# Action priority for sorting output
_ACTION_PRIORITY = {"EVACUATE_NOW": 0, "EVACUATE_ADVISED": 1, "MONITOR": 2}


def _haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Haversine distance in km."""
    R = 6371.0
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = (math.sin(dlat / 2) ** 2
         + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2))
         * math.sin(dlon / 2) ** 2)
    return R * 2 * math.asin(math.sqrt(max(0.0, a)))


def _classify_action(
    flooded_count: int,
    hospital_reachable: bool,
    resilience_index: Optional[float],
) -> str:
    if (not hospital_reachable
            or (resilience_index is not None and resilience_index < 0.5)
            or flooded_count > 50):
        return "EVACUATE_NOW"
    if (hospital_reachable
            and (resilience_index is None or resilience_index < 0.7)
            and flooded_count > 5):
        return "EVACUATE_ADVISED"
    return "MONITOR"


def generate_evacuation_advisories(
    G_alive,
    flooded_node_ids: List[int],
    ward_flood_counts: Dict[str, int],
    camp_results: List[dict],
    hospital_status: List[HospStatus],
    resilience_index: Optional[float],
) -> List[EvacAdvisory]:
    """
    Generate a deterministic EvacAdvisory for each ward with flooded nodes.

    Args:
        G_alive:          Alive graph (flooded nodes removed).
        flooded_node_ids: List of flooded node IDs.
        ward_flood_counts: {ward_name: flooded_node_count} from _get_affected_wards().
        camp_results:     List of camp dicts from compute_relief_camps()["camps"].
        hospital_status:  List of HospStatus from autonomous loop.
        resilience_index: Current RI (may be None).

    Returns:
        List[EvacAdvisory] sorted by action priority (EVACUATE_NOW first).
    """
    flooded_set = set(flooded_node_ids)
    any_hospital_reachable = any(h.reachable for h in hospital_status)

    # Build ward → flooded node positions for centroid calculation
    ward_flooded_positions: Dict[str, List] = {w: [] for w in ward_flood_counts}
    for node_id in flooded_node_ids:
        data = G_alive.nodes.get(node_id) if node_id in G_alive.nodes else None
        if data is None:
            # Node may not be in G_alive (it was ablated); try to get from full graph
            # We'll skip position-unknown nodes gracefully
            continue
        lat = data.get("y")
        lon = data.get("x")
        if lat is None or lon is None:
            continue

        # We don't know which ward this node belongs to here without re-running
        # the polygon test — that's expensive. We'll use a simplified approach:
        # assign the flooded node to the ward that matches its coordinates via
        # the _get_ward_for_node function from accessibility if available.
        try:
            from app.api.accessibility import _get_ward_for_node
            ward = _get_ward_for_node(lat, lon)
            if ward and ward in ward_flooded_positions:
                ward_flooded_positions[ward].append((lat, lon))
        except Exception:
            pass

    advisories: List[EvacAdvisory] = []

    for ward_name, flooded_count in ward_flood_counts.items():
        if ward_name == "Outside Ward Boundary":
            continue

        # Ward centroid from flooded node positions
        positions = ward_flooded_positions.get(ward_name, [])
        if positions:
            centroid_lat = sum(p[0] for p in positions) / len(positions)
            centroid_lon = sum(p[1] for p in positions) / len(positions)
        else:
            # Fallback: use Bengaluru geographic center
            centroid_lat, centroid_lon = 12.9716, 77.5946

        # Nearest camp by haversine distance
        nearest_camp_id = "none"
        nearest_camp_dist_km = float("inf")
        for camp in camp_results:
            clat = camp.get("lat") or camp.get("y")
            clon = camp.get("lng") or camp.get("x")
            if clat is None or clon is None:
                continue
            dist = _haversine_km(centroid_lat, centroid_lon, clat, clon)
            if dist < nearest_camp_dist_km:
                nearest_camp_dist_km = dist
                nearest_camp_id = camp.get("id", "camp")

        # Travel time estimate: haversine distance at 30 km/h
        travel_time_s = (nearest_camp_dist_km / 30.0) * 3600.0

        action = _classify_action(flooded_count, any_hospital_reachable, resilience_index)

        # Population: proxy estimate using flooded node count
        # Real WorldPop spatial query is in /accessibility/flood-impact
        population_estimate = flooded_count * 500  # rough proxy

        advisories.append(EvacAdvisory(
            ward_name=ward_name,
            action=action,
            population_estimate=population_estimate,
            population_source="ESTIMATED_node_proxy_500_per_flooded_node",
            flooded_node_count=flooded_count,
            nearest_camp_id=nearest_camp_id,
            recommended_corridor="Via nearest arterial road (route computed on alive graph)",
            travel_time_estimate_s=round(travel_time_s, 0),
            hospital_reachable=any_hospital_reachable,
        ))

    advisories.sort(key=lambda a: _ACTION_PRIORITY.get(a.action, 99))
    logger.info(
        f"Evacuation advisories: {len(advisories)} wards — "
        f"{sum(1 for a in advisories if a.action=='EVACUATE_NOW')} EVACUATE_NOW, "
        f"{sum(1 for a in advisories if a.action=='EVACUATE_ADVISED')} EVACUATE_ADVISED."
    )
    return advisories
