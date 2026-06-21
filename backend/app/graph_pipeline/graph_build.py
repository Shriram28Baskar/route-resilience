"""
Graph construction: convert skeleton → NetworkX graph.
Also provides GraphStore — an in-memory singleton holding the active graphs.
"""
import json
import logging
import os
from typing import Optional, Dict, Any, Tuple

import numpy as np
import networkx as nx
from scipy import ndimage

logger = logging.getLogger(__name__)

AOI_SOUTH = float(os.getenv("AOI_SOUTH", 12.92))
AOI_WEST  = float(os.getenv("AOI_WEST",  77.57))
AOI_NORTH = float(os.getenv("AOI_NORTH", 12.99))
AOI_EAST  = float(os.getenv("AOI_EAST",  77.64))


# ── Graph Store ───────────────────────────────────────────────────────────────

class GraphStore:
    _raw:             Optional[nx.Graph] = None
    _healed:          Optional[nx.Graph] = None
    _osm_fallback:    Optional[nx.Graph] = None
    _last_simulation: Optional[Dict]     = None

    @classmethod
    async def initialize(cls):
        """Attempt to load OSM fallback graph on startup."""
        try:
            cls._osm_fallback = await _load_osm_graph()
            logger.info(f"OSM fallback graph loaded: {cls._osm_fallback.number_of_nodes()} nodes")
        except Exception as exc:
            logger.warning(f"Could not load OSM fallback: {exc}. Continuing without it.")

    @classmethod
    def set_raw(cls, G: nx.Graph):
        cls._raw = G

    @classmethod
    def get_raw(cls) -> Optional[nx.Graph]:
        return cls._raw

    @classmethod
    def set_healed(cls, G: nx.Graph):
        cls._healed = G

    @classmethod
    def get_healed(cls) -> Optional[nx.Graph]:
        return cls._healed

    @classmethod
    def get_osm_fallback(cls) -> Optional[nx.Graph]:
        return cls._osm_fallback

    @classmethod
    def set_last_simulation(cls, result: Dict):
        cls._last_simulation = result

    @classmethod
    def get_last_simulation(cls) -> Optional[Dict]:
        return cls._last_simulation


# ── Skeleton → Graph ──────────────────────────────────────────────────────────

def skeleton_to_graph(skeleton: np.ndarray, pixel_to_meter: float = 1.0) -> nx.Graph:
    """
    Convert a boolean skeleton array to a weighted NetworkX graph.

    Node positions are pixel (col, row) coordinates.
    Edge weights are Euclidean pixel distances (scaled by pixel_to_meter).

    Args:
        skeleton:       Boolean (H, W) skeleton array.
        pixel_to_meter: Scale factor to convert pixel distance to metres.

    Returns:
        G: nx.Graph with node attrs {x, y} and edge attr {length, weight}.
    """
    h, w = skeleton.shape
    G = nx.Graph()

    # Index skeleton pixels
    ys, xs = np.where(skeleton)
    pixel_set = set(zip(ys.tolist(), xs.tolist()))

    # Detect intersection and endpoint pixels (degree ≠ 2)
    kernel = np.ones((3, 3), dtype=np.uint8)
    kernel[1, 1] = 0
    degree = ndimage.convolve(skeleton.astype(np.uint8), kernel, mode="constant")

    # Nodes = intersections (degree ≥ 3) + endpoints (degree == 1)
    node_pixels = {(r, c) for (r, c) in pixel_set if degree[r, c] != 2}
    if not node_pixels:
        # Fallback: use all pixels as nodes (for very small skeletons)
        node_pixels = pixel_set

    # Map pixel → node ID
    pixel_to_node: Dict[Tuple[int, int], int] = {}
    for node_id, (r, c) in enumerate(sorted(node_pixels)):
        lat, lon = _pixel_to_latlon(r, c, h, w)
        G.add_node(node_id, y=lat, x=lon, pixel_r=r, pixel_c=c)
        pixel_to_node[(r, c)] = node_id

    # Trace edges by walking the skeleton between node pixels
    visited_edges = set()
    dirs = [(-1, -1), (-1, 0), (-1, 1), (0, -1), (0, 1), (1, -1), (1, 0), (1, 1)]

    for start_px in node_pixels:
        for dr, dc in dirs:
            nr, nc = start_px[0] + dr, start_px[1] + dc
            next_px = (nr, nc)
            if next_px not in pixel_set:
                continue

            # Walk until we hit another node pixel
            path = [start_px, next_px]
            prev_px = start_px
            curr_px = next_px

            while curr_px not in node_pixels and len(path) < 10000:
                moved = False
                for ddr, ddc in dirs:
                    cand = (curr_px[0] + ddr, curr_px[1] + ddc)
                    if cand in pixel_set and cand != prev_px:
                        path.append(cand)
                        prev_px, curr_px = curr_px, cand
                        moved = True
                        break
                if not moved:
                    break

            if curr_px in node_pixels and curr_px != start_px:
                edge_key = (min(pixel_to_node[start_px], pixel_to_node[curr_px]),
                            max(pixel_to_node[start_px], pixel_to_node[curr_px]))
                if edge_key not in visited_edges:
                    length = _path_length(path) * pixel_to_meter
                    speed = 30.0  # default 30 km/h for skeleton roads
                    G.add_edge(pixel_to_node[start_px], pixel_to_node[curr_px],
                               length=length, weight=length, path_pixels=len(path),
                               speed_kph=speed, time_s=length / (speed * 1000 / 3600))
                    visited_edges.add(edge_key)

    logger.info(f"Graph built: {G.number_of_nodes()} nodes, {G.number_of_edges()} edges")
    return G


def _pixel_to_latlon(r: int, c: int, h: int, w: int) -> Tuple[float, float]:
    """Map pixel (row, col) → (lat, lon) using linear interpolation over the AOI bounding box."""
    lat = AOI_NORTH - (r / h) * (AOI_NORTH - AOI_SOUTH)
    lon = AOI_WEST  + (c / w) * (AOI_EAST  - AOI_WEST)
    return lat, lon


def _path_length(path) -> float:
    """Sum Euclidean distances along a pixel path."""
    total = 0.0
    for i in range(1, len(path)):
        dr = path[i][0] - path[i - 1][0]
        dc = path[i][1] - path[i - 1][1]
        total += (dr ** 2 + dc ** 2) ** 0.5
    return total


# ── GeoJSON serialization ─────────────────────────────────────────────────────

def graph_to_geojson(G: nx.Graph) -> dict:
    """
    Convert a NetworkX graph to a GeoJSON FeatureCollection.
    Nodes → Point features, edges → LineString features.
    """
    features = []

    for node_id, data in G.nodes(data=True):
        lon = data.get("x", 0)
        lat = data.get("y", 0)
        features.append({
            "type": "Feature",
            "geometry": {"type": "Point", "coordinates": [lon, lat]},
            "properties": {
                "id": str(node_id),
                "type": "node",
                "degree": G.degree(node_id),
                **{k: v for k, v in data.items() if k not in ("x", "y")},
            },
        })

    for u, v, data in G.edges(data=True):
        u_data = G.nodes[u]
        v_data = G.nodes[v]
        # Handle cases where OSM tags are lists (e.g., ['primary', 'primary_link'])
        hw = data.get("highway", "")
        if isinstance(hw, list):
            hw = hw[0]

        if "geometry" in data:
            import shapely.geometry
            if isinstance(data["geometry"], shapely.geometry.LineString):
                coords = list(data["geometry"].coords)
            else:
                coords = [
                    [u_data.get("x", 0), u_data.get("y", 0)],
                    [v_data.get("x", 0), v_data.get("y", 0)],
                ]
        else:
            coords = [
                [u_data.get("x", 0), u_data.get("y", 0)],
                [v_data.get("x", 0), v_data.get("y", 0)],
            ]

        features.append({
            "type": "Feature",
            "geometry": {
                "type": "LineString",
                "coordinates": coords,
            },
            "properties": {
                "source": str(u),
                "target": str(v),
                "type": "edge",
                "highway": str(hw),
                "length": data.get("length", 0),
                "weight": data.get("weight", 0),
            },
        })

    return {"type": "FeatureCollection", "features": features}


# ── OSM fallback loader ───────────────────────────────────────────────────────

SPEED_LIMITS = {
    "motorway": 80.0,
    "trunk": 70.0,
    "primary": 60.0,
    "secondary": 50.0,
    "tertiary": 40.0,
    "residential": 30.0,
    "unclassified": 30.0,
    "living_street": 15.0,
}

def _parse_speed_limit(data: dict) -> float:
    maxspeed = data.get("maxspeed")
    if maxspeed:
        if isinstance(maxspeed, list):
            maxspeed = maxspeed[0]
        try:
            digits = "".join(filter(str.isdigit, str(maxspeed)))
            if digits:
                return float(digits)
        except Exception:
            pass
    highway = data.get("highway")
    if highway:
        if isinstance(highway, list):
            highway = highway[0]
        return SPEED_LIMITS.get(highway, 30.0)
    return 30.0

async def _load_osm_graph() -> nx.Graph:
    """
    Load the road network for the configured AOI from OpenStreetMap via OSMnx.
    Results are cached to data/graphs/osm_fallback.gpickle.
    """
    import osmnx as ox
    import pickle

    cache_path = "data/graphs/osm_fallback.gpickle"
    os.makedirs("data/graphs", exist_ok=True)

    if os.path.exists(cache_path):
        logger.info("Loading OSM graph from cache …")
        with open(cache_path, "rb") as f:
            G = pickle.load(f)
        G.graph["is_osm_fallback"] = True
        # Ensure all edges have speed_kph and time_s computed, even if loaded from an old cache
        updated = False
        for u, v, data in G.edges(data=True):
            if "time_s" not in data:
                length = data.get("length", 1.0)
                speed = _parse_speed_limit(data)
                data["speed_kph"] = speed
                data["time_s"] = length / (speed * 1000 / 3600)
                updated = True
        if updated:
            logger.info("Updating cached OSM graph with speed/time attributes ...")
            with open(cache_path, "wb") as f:
                pickle.dump(G, f)
        return G

    logger.info(f"Downloading OSM graph for AOI ({AOI_SOUTH},{AOI_WEST},{AOI_NORTH},{AOI_EAST}) …")
    G_osm = ox.graph_from_bbox(
        north=AOI_NORTH, south=AOI_SOUTH, east=AOI_EAST, west=AOI_WEST,
        network_type="drive",
        simplify=True,
    )
    G = ox.convert.to_undirected(G_osm)
    G.graph["is_osm_fallback"] = True

    # Standardize node attributes
    for node_id, data in G.nodes(data=True):
        data["x"] = data.get("x", data.get("lon", 0.0))
        data["y"] = data.get("y", data.get("lat", 0.0))

    # Standardize edge attributes
    for u, v, data in G.edges(data=True):
        length = data.get("length", 1.0)
        data["weight"] = length
        data["length"] = length
        speed = _parse_speed_limit(data)
        data["speed_kph"] = speed
        data["time_s"] = length / (speed * 1000 / 3600)

    with open(cache_path, "wb") as f:
        pickle.dump(G, f)

    return G
