"""
Nominatim geocoding: convert place names / addresses → (lat, lon).
"""
import logging
import os
from typing import Optional, Tuple

import httpx

logger = logging.getLogger(__name__)
NOMINATIM_URL = os.getenv("NOMINATIM_URL", "https://nominatim.openstreetmap.org")


async def geocode(query: str, country_code: str = "IN") -> Optional[Tuple[float, float]]:
    """
    Geocode a place name or address string.

    Returns:
        (lat, lon) tuple, or None if not found.
    """
    params = {
        "q": query,
        "format": "json",
        "limit": 1,
        "countrycodes": country_code,
    }
    headers = {"User-Agent": "RouteResilience/1.0 (hackathon@isro-nnrms)"}

    try:
        async with httpx.AsyncClient(timeout=10) as client:
            response = await client.get(f"{NOMINATIM_URL}/search", params=params, headers=headers)
            response.raise_for_status()
            results = response.json()
    except httpx.HTTPError as exc:
        logger.error(f"Nominatim error: {exc}")
        return None

    if not results:
        logger.warning(f"Nominatim: no results for '{query}'")
        return None

    lat = float(results[0]["lat"])
    lon = float(results[0]["lon"])
    logger.info(f"Geocoded '{query}' → ({lat}, {lon})")
    return lat, lon


async def reverse_geocode(lat: float, lon: float) -> Optional[str]:
    """Reverse geocode (lat, lon) → display name."""
    params = {"lat": lat, "lon": lon, "format": "json"}
    headers = {"User-Agent": "RouteResilience/1.0 (hackathon@isro-nnrms)"}

    try:
        async with httpx.AsyncClient(timeout=10) as client:
            response = await client.get(f"{NOMINATIM_URL}/reverse", params=params, headers=headers)
            response.raise_for_status()
            result = response.json()
        return result.get("display_name")
    except httpx.HTTPError as exc:
        logger.error(f"Nominatim reverse geocode error: {exc}")
        return None
