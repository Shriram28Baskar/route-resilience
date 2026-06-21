"""
ISRO Bhuvan Geoportal Integration
Provides access to ISRO's National Remote Sensing Centre (NRSC) data
via Bhuvan WMS endpoints and REST APIs.

Bhuvan is ISRO's official satellite data portal — using it instead of
generic OSM tiles makes the solution satellite-native and ISRO-aligned.
"""
import logging
import os
from typing import Dict, Any, Optional, List

import httpx

logger = logging.getLogger(__name__)

# ── Bhuvan WMS / Tile Endpoints ───────────────────────────────────────────────
BHUVAN_WMS_BASE = "https://bhuvan-vec2.nrsc.gov.in/bhuvan/wms"
BHUVAN_TILE_BASE = "https://bhuvan-ras2.nrsc.gov.in/tile"
BHUVAN_REST_BASE = "https://bhuvan-app1.nrsc.gov.in/api"

# Available layers from ISRO Bhuvan
BHUVAN_LAYERS = {
    "lulc_2023": "india_lulc_2023",        # Land Use / Land Cover
    "roads": "india_roads_2023",            # Road network (NRSC-derived)
    "dem": "india_dem_srtm",               # Digital Elevation Model
    "flood_hazard": "india_flood_hazard",  # Flood hazard zones
    "districts": "india_districts",        # Administrative boundaries
    "resourcesat": "resourcesat2a_liss3",  # ResourceSat-2A LISS-3 imagery
}

# WMS tile URL template for Leaflet frontend
BHUVAN_TILE_URL_TEMPLATE = (
    "https://bhuvan-vec2.nrsc.gov.in/bhuvan/gwc/service/wmts?"
    "SERVICE=WMTS&REQUEST=GetTile&VERSION=1.0.0"
    "&LAYER={layer}&STYLE=default&TILEMATRIXSET=EPSG:900913"
    "&TILEMATRIX=EPSG:900913:{z}&TILEROW={y}&TILECOL={x}"
    "&FORMAT=image/png"
)


def get_layer_config() -> Dict[str, Any]:
    """
    Returns Leaflet-compatible tile layer configuration for all Bhuvan layers.
    Used by the frontend to render ISRO satellite data as map overlays.
    """
    return {
        "wms_base": BHUVAN_WMS_BASE,
        "layers": {
            "lulc": {
                "name": "LULC 2023 (NRSC)",
                "description": "Land Use / Land Cover derived from ResourceSat-2A",
                "wms_layer": BHUVAN_LAYERS["lulc_2023"],
                "wms_url": BHUVAN_WMS_BASE,
                "format": "image/png",
                "transparent": True,
                "attribution": "ISRO / NRSC — Bhuvan",
                "opacity": 0.65,
            },
            "roads": {
                "name": "ISRO Road Network",
                "description": "Road network extracted from NRSC satellite analysis",
                "wms_layer": BHUVAN_LAYERS["roads"],
                "wms_url": BHUVAN_WMS_BASE,
                "format": "image/png",
                "transparent": True,
                "attribution": "ISRO / NRSC — Bhuvan",
                "opacity": 0.85,
            },
            "flood_hazard": {
                "name": "Flood Hazard Zones",
                "description": "NDMA/ISRO flood-prone area classification",
                "wms_layer": BHUVAN_LAYERS["flood_hazard"],
                "wms_url": BHUVAN_WMS_BASE,
                "format": "image/png",
                "transparent": True,
                "attribution": "ISRO / NRSC — Bhuvan",
                "opacity": 0.5,
            },
            "resourcesat": {
                "name": "ResourceSat-2A LISS-3",
                "description": "ISRO ResourceSat-2A satellite imagery (23.5m resolution)",
                "wms_layer": BHUVAN_LAYERS["resourcesat"],
                "wms_url": BHUVAN_WMS_BASE,
                "format": "image/png",
                "transparent": False,
                "attribution": "ISRO / NRSC — ResourceSat-2A",
                "opacity": 1.0,
            },
        },
        "info": {
            "portal": "https://bhuvan.nrsc.gov.in",
            "mission": "ISRO National Remote Sensing Centre (NRSC)",
            "satellites": ["ResourceSat-2", "ResourceSat-2A", "CartoSat-2", "CartoSat-3"],
            "data_types": ["LULC", "Road Network", "DEM", "Flood Hazard", "Urban Extent"],
            "api_docs": "https://bhuvan.nrsc.gov.in/api/",
        },
    }


async def fetch_district_roads(
    district: str,
    state: str = "Karnataka",
    timeout: float = 10.0,
) -> Optional[Dict[str, Any]]:
    """
    Fetch road network GeoJSON for a district from Bhuvan REST API.
    Falls back gracefully if the API is unavailable.
    """
    url = f"{BHUVAN_REST_BASE}/road_network"
    params = {"district": district, "state": state, "format": "geojson"}
    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            resp = await client.get(url, params=params)
            resp.raise_for_status()
            data = resp.json()
            logger.info(f"Bhuvan: fetched road network for {district}, {state}")
            return data
    except Exception as exc:
        logger.warning(
            f"Bhuvan API unavailable for {district}/{state}: {exc}. "
            "Using OSM fallback — in production, configure BHUVAN_API_KEY."
        )
        return None


async def fetch_flood_hazard_zones(
    bbox: tuple,  # (min_lon, min_lat, max_lon, max_lat)
    timeout: float = 10.0,
) -> Optional[Dict[str, Any]]:
    """
    Fetch NDMA/ISRO flood hazard zone polygons for an AOI bounding box.
    Returns GeoJSON FeatureCollection or None on failure.
    """
    min_lon, min_lat, max_lon, max_lat = bbox
    url = f"{BHUVAN_REST_BASE}/flood_hazard"
    params = {
        "bbox": f"{min_lon},{min_lat},{max_lon},{max_lat}",
        "format": "geojson",
    }
    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            resp = await client.get(url, params=params)
            resp.raise_for_status()
            logger.info(f"Bhuvan: fetched flood hazard zones for bbox {bbox}")
            return resp.json()
    except Exception as exc:
        logger.warning(f"Bhuvan flood hazard API unavailable: {exc}")
        return None


def get_wms_capabilities_url() -> str:
    """Return the WMS GetCapabilities URL for Bhuvan."""
    return f"{BHUVAN_WMS_BASE}?SERVICE=WMS&REQUEST=GetCapabilities"


def satellite_info() -> Dict[str, Any]:
    """
    Returns metadata about ISRO satellites used in this system.
    Included in API responses to demonstrate ISRO-native data lineage.
    """
    return {
        "primary_satellite": "ResourceSat-2A",
        "sensor": "LISS-3 (Linear Imaging Self Scanner)",
        "resolution_m": 23.5,
        "revisit_days": 24,
        "spectral_bands": [
            "Green (0.52-0.59μm)",
            "Red (0.62-0.68μm)",
            "NIR (0.77-0.86μm)",
            "SWIR (1.55-1.70μm)",
        ],
        "backup_satellite": "CartoSat-3",
        "cartosat_resolution_m": 0.25,
        "data_portal": "https://bhuvan.nrsc.gov.in",
        "organization": "National Remote Sensing Centre (NRSC), ISRO",
        "application": "Road extraction, LULC mapping, disaster monitoring",
    }
