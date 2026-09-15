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


def _read_hgt_bilinear(filepath: str, lat: float, lon: float) -> Optional[float]:
    """Read a continuous elevation by bilinearly interpolating four HGT cells.

    SRTM samples are integral metres, but graph nodes are not constrained to
    sample centres.  Nearest-cell lookup creates artificial 1 m terraces that
    make centimetre-scale runoff projections empty.  Bilinear interpolation is
    a local, deterministic representation of the same DEM; it does not claim
    sub-metre terrain measurement accuracy or add external data.
    """
    samples, tile_lat, tile_lon = _hgt_meta(filepath)
    if not (tile_lat <= lat < tile_lat + 1 and tile_lon <= lon < tile_lon + 1):
        return None

    row_f = (tile_lat + 1 - lat) * (samples - 1)
    col_f = (lon - tile_lon) * (samples - 1)
    row0 = max(0, min(int(math.floor(row_f)), samples - 1))
    col0 = max(0, min(int(math.floor(col_f)), samples - 1))
    row1 = min(row0 + 1, samples - 1)
    col1 = min(col0 + 1, samples - 1)
    row_weight = row_f - row0
    col_weight = col_f - col0

    def read_sample(handle, row: int, col: int) -> Optional[float]:
        handle.seek((row * samples + col) * 2)
        raw = handle.read(2)
        if len(raw) != 2:
            return None
        value = struct.unpack(">h", raw)[0]
        return None if value == -32768 else float(value)

    with open(filepath, "rb") as hgt:
        northwest = read_sample(hgt, row0, col0)
        northeast = read_sample(hgt, row0, col1)
        southwest = read_sample(hgt, row1, col0)
        southeast = read_sample(hgt, row1, col1)

    if any(value is None for value in (northwest, northeast, southwest, southeast)):
        return None

    north = northwest * (1.0 - col_weight) + northeast * col_weight
    south = southwest * (1.0 - col_weight) + southeast * col_weight
    return north * (1.0 - row_weight) + south * row_weight


def get_elevation(lat: float, lon: float) -> Tuple[Optional[float], str]:
    """
    Return (elevation_m, source_label) for a WGS84 point.

    source_label is one of:
      'SRTMGL1_30m'   — from the 1-arcsecond tile
      'SRTM3_90m'     — from the 3-arcsecond tile
      'unknown'       — no HGT file covers this point
    """
    for filepath in HGT_FILES:
        val = _read_hgt_bilinear(filepath, lat, lon)
        if val is not None:
            size = os.path.getsize(filepath)
            source = "SRTMGL1_30m_bilinear" if size == 25934402 else "SRTM3_90m_bilinear"
            return val, source
    return None, "unknown"


def initialize_elevations(G: nx.Graph) -> None:
    """
    Stamp every node in G with continuous, locally interpolated 'elevation'
    (m) and an explicit 'elevation_source'.

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
            G.nodes[n]["elevation_interpolation"] = "bilinear"
            G.nodes[n]["elevation_unknown"] = False
            ok += 1
        else:
            G.nodes[n]["elevation"] = None
            G.nodes[n]["elevation_source"] = "unknown"
            G.nodes[n]["elevation_unknown"] = True
    # Compute local topographic sink index and depression depth:
    for n in G.nodes():
        z = G.nodes[n].get("elevation")
        if z is None:
            G.nodes[n]["local_sink_delta"] = 0.0
            G.nodes[n]["depression_depth"] = 0.0
            continue
        nbrs = list(G.neighbors(n))
        if nbrs:
            nbr_z = [G.nodes[m].get("elevation") for m in nbrs if G.nodes[m].get("elevation") is not None]
            if nbr_z:
                mean_z = sum(nbr_z) / len(nbr_z)
                G.nodes[n]["depression_depth"] = max(0.0, mean_z - z)
            else:
                G.nodes[n]["depression_depth"] = 0.0
        else:
            G.nodes[n]["depression_depth"] = 0.0

        nbrs2 = set(nbrs)
        for nbr in nbrs:
            nbrs2.update(G.neighbors(nbr))
        nbr_z2 = [G.nodes[m].get("elevation") for m in nbrs2 if G.nodes[m].get("elevation") is not None]
        if nbr_z2:
            G.nodes[n]["local_sink_delta"] = max(0.0, z - min(nbr_z2))
        else:
            G.nodes[n]["local_sink_delta"] = 0.0

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


def flood_ablate_basin_aware(G: nx.Graph, rainfall_mm: float | dict) -> List:
    """Return flooded node IDs using basin-aware per-watershed water levels
    and dual-mechanism (fluvial valley accumulation + pluvial sag pooling) modeling.

    Hydrological Inundation Mechanisms:
      1. Valley Axis Accumulation (Fluvial backwater):
         Low-lying roads near basin lake/river outlets flood as runoff converges
         down the watershed axis: (z_n - DEM_MIN) <= valley_head(R).
      2. Local Sag / Underpass Pooling (Pluvial flash flooding):
         Road segments sitting in local depressions (D_n = mean_nbr_elev - z_n)
         accumulate runoff shed from connecting road segments. Deeper sags
         submerge at lower rainfall intensities.

    Guarantees:
      - Strict Monotonicity: Flooded(R1) ⊆ Flooded(R2) for R1 < R2.
      - 100% Cross-basin isolation: rain=0 in a basin causes exactly 0 flooded nodes.
    """
    from app.data.backtest import (
        assign_basin, BASINS, initialize_basin_mins,
        URBAN_RUNOFF_COEFFICIENT,
    )

    initialize_elevations(G)
    initialize_basin_mins(G)

    flooded = []
    for n, data in G.nodes(data=True):
        elev = data.get("elevation")
        if elev is None:
            continue
        lat = data.get("y")
        lon = data.get("x")
        if lat is None or lon is None:
            continue
        basin_id = assign_basin(lat, lon)
        rain_val = (
            rainfall_mm.get(basin_id, 0.0)
            if isinstance(rainfall_mm, dict)
            else float(rainfall_mm)
        )
        if rain_val <= 0.0:
            continue

        dem_min = BASINS[basin_id]["dem_min_m"]
        eff_runoff_m = (rain_val * URBAN_RUNOFF_COEFFICIENT) / 1000.0
        valley_head = eff_runoff_m * 6.0
        req_dep = max(0.2, 6.0 - (rain_val ** 0.45) * 0.6)

        # Mechanism 1: Fluvial / valley backwater near lake/channel outlet
        if (elev - dem_min) <= valley_head:
            flooded.append(n)
        # Mechanism 2: Pluvial sag / underpass accumulation across urban terrain
        elif data.get("depression_depth", 0.0) >= req_dep:
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
