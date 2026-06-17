#!/usr/bin/env python3
"""
Download and cache all required data for the Route Resilience demo.

Run this script BEFORE starting the backend server to pre-warm:
  1. OSM road graph for the Bengaluru AOI (via OSMnx)
  2. Hospital POIs (via Overpass API)

Usage:
    cd backend
    python scripts/download_data.py
"""
import asyncio
import logging
import os
import pickle
import sys
from pathlib import Path

logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)s | %(message)s")
logger = logging.getLogger(__name__)

# Add parent to path so app imports work
sys.path.insert(0, str(Path(__file__).parent.parent))


async def download_osm_graph():
    import osmnx as ox

    south = float(os.getenv("AOI_SOUTH", "12.92"))
    west  = float(os.getenv("AOI_WEST",  "77.57"))
    north = float(os.getenv("AOI_NORTH", "12.99"))
    east  = float(os.getenv("AOI_EAST",  "77.64"))

    cache_path = Path("data/graphs/osm_fallback.gpickle")
    cache_path.parent.mkdir(parents=True, exist_ok=True)

    if cache_path.exists():
        logger.info(f"OSM graph already cached at {cache_path}. Skipping download.")
        return

    logger.info(f"Downloading OSM road network for bbox ({south},{west},{north},{east}) …")
    G_osm = ox.graph_from_bbox(north=north, south=south, east=east, west=west,
                                network_type="drive", simplify=True)
    G = ox.convert.to_undirected(G_osm)

    for node_id, data in G.nodes(data=True):
        data["x"] = data.get("x", data.get("lon", 0.0))
        data["y"] = data.get("y", data.get("lat", 0.0))
    for u, v, data in G.edges(data=True):
        length = data.get("length", 1.0)
        data["weight"] = length
        data["length"] = length

    with open(cache_path, "wb") as f:
        pickle.dump(G, f)
    logger.info(f"✓ OSM graph saved: {G.number_of_nodes()} nodes, {G.number_of_edges()} edges → {cache_path}")


async def download_hospitals():
    from app.integrations.overpass import fetch_hospitals

    south = float(os.getenv("AOI_SOUTH", "12.92"))
    west  = float(os.getenv("AOI_WEST",  "77.57"))
    north = float(os.getenv("AOI_NORTH", "12.99"))
    east  = float(os.getenv("AOI_EAST",  "77.64"))

    logger.info("Fetching hospital POIs from Overpass …")
    hospitals = await fetch_hospitals(south=south, west=west, north=north, east=east)
    logger.info(f"✓ Found {len(hospitals)} hospitals, cached to data/cache/")


async def main():
    os.makedirs("data/graphs",       exist_ok=True)
    os.makedirs("data/cache",        exist_ok=True)
    os.makedirs("data/checkpoints",  exist_ok=True)
    os.makedirs("data/rasters",      exist_ok=True)
    os.makedirs("data/masks",        exist_ok=True)

    await download_osm_graph()
    await download_hospitals()

    logger.info("\n✅ All data downloaded. You can now start the backend: uvicorn app.main:app --reload")


if __name__ == "__main__":
    asyncio.run(main())
