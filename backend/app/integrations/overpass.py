"""
Overpass API integration: fetch hospital and emergency service POIs
within a bounding box.
"""
import json
import logging
import os
from pathlib import Path
from typing import List, Dict

import httpx

logger = logging.getLogger(__name__)

OVERPASS_URL = os.getenv("OVERPASS_URL", "https://overpass-api.de/api/interpreter")
CACHE_DIR = Path("data/cache")


async def fetch_facilities(
    south: float, west: float, north: float, east: float,
    use_cache: bool = True,
    amenities: List[str] = ["hospital", "clinic", "health_post", "pharmacy", "ambulance_station"]
) -> List[Dict]:
    """
    Fetch facility POIs from Overpass API for the given bounding box.
    Results are cached to disk to avoid repeated API calls during demo.

    Returns:
        List of dicts: { "name": str, "lat": float, "lon": float, "osm_id": str, "amenity": str }
    """
    amenity_hash = "_".join(sorted(amenities))
    cache_key = f"facilities_{south:.4f}_{west:.4f}_{north:.4f}_{east:.4f}_{amenity_hash}.json"
    cache_path = CACHE_DIR / cache_key

    CACHE_DIR.mkdir(parents=True, exist_ok=True)

    if use_cache and cache_path.exists():
        logger.info(f"Loading hospitals from cache: {cache_path}")
        return json.loads(cache_path.read_text())

    query_nodes = "".join([f'node["amenity"="{am}"]({south},{west},{north},{east});\n      ' for am in amenities])
    query_ways = "".join([f'way["amenity"="{am}"]({south},{west},{north},{east});\n      ' for am in amenities])
    
    query = f"""
    [out:json][timeout:30];
    (
      {query_nodes}
      {query_ways}
    );
    out center;
    """

    logger.info(f"Fetching {len(amenities)} amenities from Overpass API for bbox ({south},{west},{north},{east})")

    headers = {
        "User-Agent": "RouteResilience/1.0 (hackathon@isro-nnrms)"
    }

    try:
        async with httpx.AsyncClient(timeout=35) as client:
            response = await client.post(OVERPASS_URL, data={"data": query}, headers=headers)
            response.raise_for_status()
            data = response.json()
    except httpx.HTTPError as exc:
        logger.error(f"Overpass API error: {exc}")
        return _static_fallback_facilities(south, west, north, east)

    hospitals = []
    for element in data.get("elements", []):
        if element["type"] == "node":
            lat, lon = element["lat"], element["lon"]
        elif "center" in element:
            lat, lon = element["center"]["lat"], element["center"]["lon"]
        else:
            continue

        hospitals.append({
            "name": element.get("tags", {}).get("name", "Unknown Hospital"),
            "lat": lat,
            "lon": lon,
            "osm_id": str(element.get("id", "")),
            "amenity": element.get("tags", {}).get("amenity", "hospital"),
        })

    logger.info(f"Found {len(hospitals)} facilities via Overpass")

    # Cache the result
    cache_path.write_text(json.dumps(hospitals, indent=2))
    return hospitals

async def fetch_hospitals(south: float, west: float, north: float, east: float, use_cache: bool = True) -> List[Dict]:
    """Legacy wrapper for backward compatibility."""
    return await fetch_facilities(south, west, north, east, use_cache, ["hospital", "clinic", "health_post"])


def _static_fallback_facilities(south, west, north, east) -> List[Dict]:
    """Static fallback data for Bengaluru demo AOI if Overpass is down."""
    all_facilities = [
        {"name": "Manipal Hospital", "lat": 12.9538, "lon": 77.6486, "osm_id": "static_1", "amenity": "hospital"},
        {"name": "St. John's Medical College", "lat": 12.9328, "lon": 77.6226, "osm_id": "static_2", "amenity": "hospital"},
        {"name": "Sakra World Hospital", "lat": 12.9390, "lon": 77.6910, "osm_id": "static_3", "amenity": "hospital"},
        {"name": "Apollo Pharmacy (Indiranagar)", "lat": 12.9782, "lon": 77.6400, "osm_id": "static_4", "amenity": "pharmacy"},
        {"name": "MedPlus (Koramangala)", "lat": 12.9350, "lon": 77.6240, "osm_id": "static_5", "amenity": "pharmacy"},
        {"name": "108 Ambulance Station", "lat": 12.9650, "lon": 77.6000, "osm_id": "static_6", "amenity": "ambulance_station"},
    ]
    # Filter to bbox
    return [
        h for h in all_facilities
        if south <= h["lat"] <= north and west <= h["lon"] <= east
    ]
