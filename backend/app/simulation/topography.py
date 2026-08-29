"""
Topography module — reads real SRTM HGT elevation data for each graph node.

Data source: SRTMGL1 (1-arcsecond, ~30m resolution) HGT files.
Tiles used  : N12E077 and N13E077 (covering Bengaluru AOI lat 12-14, lon 77-78).

Every node gets an 'elevation' (meters, WGS84 ellipsoidal height) and an
'elevation_source' tag so the API can report data provenance transparently.

This module intentionally does NOT use rasterio so that it has zero
extra dependencies beyond the stdlib struct module.
"""

import os
import math
import struct
import logging
import networkx as nx
from typing import List, Tuple, Optional

logger = logging.getLogger(__name__)


# ── HGT file paths (portable — relative to this file, with env override) ──────
def _default_hgt_files() -> List[str]:
    """
    Compute default HGT file paths relative to this module's location.
    Override with HGT_DIR env variable for Docker/CI deployments.

    Expects DataSet directory at: <repo_root>/DataSet/
    Repo root is 4 levels up from backend/app/simulation/topography.py.
    """
    hgt_dir_override = os.getenv("HGT_DIR")
    if hgt_dir_override:
        # Env override: scan for all .hgt files in specified directory
        candidates = []
        for root, _, files in os.walk(hgt_dir_override):
            for fname in files:
                if fname.lower().endswith(".hgt"):
                    candidates.append(os.path.join(root, fname))
        return candidates

    # Default: relative navigation from this file to repo root / DataSet /
    # topography.py is at: <repo_root>/backend/app/simulation/topography.py
    # So repo_root is 3 directories up from this file's directory.
    this_dir = os.path.dirname(os.path.abspath(__file__))
    repo_root = os.path.normpath(os.path.join(this_dir, "..", "..", ".."))
    dataset_dir = os.path.join(repo_root, "DataSet")

    return [
        os.path.join(dataset_dir, "N12E077.SRTMGL1.hgt", "N12E077.hgt"),
        os.path.join(dataset_dir, "N12E077.hgt", "N12E077.hgt"),
        os.path.join(dataset_dir, "N13E077.SRTMGL1.hgt", "N12E077.hgt"),
    ]

HGT_FILES: List[str] = [p for p in _default_hgt_files() if os.path.exists(p)]


# Cache: filepath → (samples_per_side, tile_lat_sw, tile_lon_sw)
_HGT_META: dict = {}

# Node-elevation cache: node_id → elevation_m
_ELEVATION_CACHE: dict = {}


def _hgt_meta(filepath: str):
    """Return (samples, tile_lat_sw, tile_lon_sw) for an HGT file, cached."""
    if filepath in _HGT_META:
        return _HGT_META[filepath]
    size = os.path.getsize(filepath)
    if size == 25934402:
        samples = 3601           # SRTMGL1 1-arcsec ~30m
    elif size == 2884802:
        samples = 1201           # SRTM3   3-arcsec ~90m
    else:
        samples = int(math.isqrt(size // 2))

    name = os.path.basename(filepath).upper()
    lat_sign = 1 if name[0] == 'N' else -1
    lon_sign = 1 if name[3] == 'E' else -1
    tile_lat = lat_sign * int(name[1:3])
    tile_lon = lon_sign * int(name[4:7])

    meta = (samples, tile_lat, tile_lon)
    _HGT_META[filepath] = meta
    return meta


def _read_hgt(filepath: str, lat: float, lon: float) -> Optional[float]:
    """
    Read elevation (m) for (lat, lon) from one HGT tile.
    Returns None if the point is outside this tile or if the value is a void.
    """
    samples, tile_lat, tile_lon = _hgt_meta(filepath)
    if not (tile_lat <= lat < tile_lat + 1 and tile_lon <= lon < tile_lon + 1):
        return None
    row = int((tile_lat + 1 - lat) * (samples - 1))
    col = int((lon - tile_lon) * (samples - 1))
    row = max(0, min(row, samples - 1))
    col = max(0, min(col, samples - 1))
    offset = (row * samples + col) * 2
    with open(filepath, "rb") as f:
        f.seek(offset)
        raw = f.read(2)
    if len(raw) < 2:
        return None
    val = struct.unpack(">h", raw)[0]   # big-endian signed int16
    return float(val) if val != -32768 else None


def get_elevation(lat: float, lon: float) -> Tuple[Optional[float], str]:
    """
    Return (elevation_m, source_label) for a WGS84 point.

    source_label is one of:
      'SRTMGL1_30m'   — from the 1-arcsecond tile
      'SRTM3_90m'     — from the 3-arcsecond tile
      'unknown'       — no HGT file covers this point
    """
    for filepath in HGT_FILES:
        val = _read_hgt(filepath, lat, lon)
        if val is not None:
            size = os.path.getsize(filepath)
            source = "SRTMGL1_30m" if size == 25934402 else "SRTM3_90m"
            return val, source
    return None, "unknown"


def initialize_elevations(G: nx.Graph) -> None:
    """
    Stamp every node in G with 'elevation' (m) and 'elevation_source'.

    Called lazily on first flood simulation so it only runs once per
    graph lifetime. Subsequent calls are no-ops.
    """
    # Check if already stamped
    first = next(iter(G.nodes()), None)
    if first is not None and "elevation" in G.nodes[first]:
        return

    if not HGT_FILES:
        logger.warning(
            "No HGT files found. Node elevations will be marked unknown. "
            "Flood simulation will be unreliable."
        )
        for n in G.nodes():
            G.nodes[n]["elevation"] = None
            G.nodes[n]["elevation_source"] = "unknown"
            G.nodes[n]["elevation_unknown"] = True
        return

    ok = 0
    missing = 0
    for n, data in G.nodes(data=True):
        lat = data.get("y")
        lon = data.get("x")
        if lat is None or lon is None:
            G.nodes[n]["elevation"] = None
            G.nodes[n]["elevation_source"] = "unknown"
            G.nodes[n]["elevation_unknown"] = True
            missing += 1
            continue

        elev, source = get_elevation(lat, lon)
        if elev is not None:
            G.nodes[n]["elevation"] = elev
            G.nodes[n]["elevation_source"] = source
            G.nodes[n]["elevation_unknown"] = False
            ok += 1
        else:
            G.nodes[n]["elevation"] = None
            G.nodes[n]["elevation_source"] = "unknown"
            G.nodes[n]["elevation_unknown"] = True
            missing += 1

    logger.info(
        f"Elevation stamping complete: {ok} nodes from HGT, {missing} nodes unknown."
    )


def flood_ablate(G: nx.Graph, water_level: float) -> List:
    """
    Return node IDs whose real terrain elevation is at or below water_level (m).

    Nodes with unknown elevation are conservatively NOT flooded (they are
    explicitly excluded rather than silently included or excluded).

    This is an explicit approximation: we model inundation as static water
    pooling at a fixed level, not dynamic flow. The API response labels this
    as 'static_dem_approximation'.
    """
    initialize_elevations(G)
    flooded = []
    for n, data in G.nodes(data=True):
        elev = data.get("elevation")
        if elev is not None and elev <= water_level:
            flooded.append(n)
    return flooded


def get_elevation_bounds(G: nx.Graph) -> dict:
    """
    Return {min, max, mean, unknown_count} elevation stats across all graph nodes.
    Used to set the flood slider range in the frontend.
    """
    initialize_elevations(G)
    known = [
        data["elevation"]
        for _, data in G.nodes(data=True)
        if data.get("elevation") is not None
    ]
    unknown_count = G.number_of_nodes() - len(known)
    if not known:
        return {"min": 850.0, "max": 950.0, "mean": 900.0, "unknown_count": G.number_of_nodes()}
    return {
        "min": min(known),
        "max": max(known),
        "mean": round(sum(known) / len(known), 1),
        "unknown_count": unknown_count,
    }

