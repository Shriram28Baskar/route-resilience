"""
DEM-based flood ablation.

rasterio is imported lazily: it is needed only when a DEM is actually sampled,
and a hard top-level import made the ENTIRE simulation router unimportable
without the raster stack installed.
"""
import logging
import os
from typing import List, Tuple

import networkx as nx

logger = logging.getLogger(__name__)


class DEMUnavailable(RuntimeError):
    """Raised when elevations are requested but no DEM can be read."""


# Relative to where the backend server runs
DEM_PATH = "data/rasters/dem.tif"

def initialize_elevations(G: nx.MultiDiGraph):
    """Lazily load elevations into the graph nodes if they don't exist."""
    first_node = next(iter(G.nodes()), None)
    if first_node is not None and 'elevation' in G.nodes[first_node]:
        return

    if not os.path.exists(DEM_PATH):
        # Previously every node was assigned a constant 900.0 m, which turned the
        # flood model into a global on/off switch at that constant while still
        # emitting impact numbers. Callers must handle absence explicitly.
        raise DEMUnavailable(
            f"No DEM at {DEM_PATH}. Elevation-dependent results are unavailable; "
            f"see backend/data/README.md."
        )

    try:
        import rasterio
    except ImportError as exc:
        raise DEMUnavailable(
            f"rasterio is not installed, so the DEM at {DEM_PATH} cannot be read. "
            f"Install requirements-raster.txt."
        ) from exc

    try:
        logger.info("Loading elevations from %s", DEM_PATH)
        with rasterio.open(DEM_PATH) as src:
            for node, data in G.nodes(data=True):
                lat = data.get('y')
                lon = data.get('x')
                if lat and lon:
                    try:
                        found_val = False
                        for val in src.sample([(lon, lat)]):
                            v = float(val[0])
                            if v < 0: # nodata value like -32768
                                G.nodes[node]['elevation'] = 900.0
                                G.nodes[node]['elevation_unknown'] = True
                            else:
                                G.nodes[node]['elevation'] = v
                                G.nodes[node]['elevation_unknown'] = False
                            found_val = True
                            break
                        if not found_val:
                            G.nodes[node]['elevation'] = 900.0
                            G.nodes[node]['elevation_unknown'] = True
                    except Exception:
                        G.nodes[node]['elevation'] = 900.0
                        G.nodes[node]['elevation_unknown'] = True
                else:
                    G.nodes[node]['elevation'] = 900.0
                    G.nodes[node]['elevation_unknown'] = True
        logger.info("Elevations loaded from DEM.")
    except Exception as e:
        raise DEMUnavailable(f"Failed to read DEM at {DEM_PATH}: {e}") from e

def flood_ablate(G: nx.MultiDiGraph, water_level: float) -> List[int]:
    """Returns a list of node IDs that are at or below the given water_level."""
    initialize_elevations(G)
    flooded_nodes = [n for n, data in G.nodes(data=True) if data.get('elevation', 900.0) <= water_level]
    return flooded_nodes

def get_elevation_bounds(G: nx.MultiDiGraph) -> Tuple[float, float]:
    """Returns the (min, max) elevation in the graph."""
    initialize_elevations(G)
    elevations = [data.get('elevation', 900.0) for _, data in G.nodes(data=True)]
    if not elevations:
        return 850.0, 950.0
    return min(elevations), max(elevations)
