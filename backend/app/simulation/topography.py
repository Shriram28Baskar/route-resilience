import rasterio
import networkx as nx
from typing import List, Tuple
import os

# Relative to where the backend server runs
DEM_PATH = "data/rasters/dem.tif"

def initialize_elevations(G: nx.MultiDiGraph):
    """Lazily load elevations into the graph nodes if they don't exist."""
    first_node = next(iter(G.nodes()), None)
    if first_node is not None and 'elevation' in G.nodes[first_node]:
        return

    GEOID_OFFSET = 820.0
    if not os.path.exists(DEM_PATH):
        print(f"Warning: DEM file not found at {DEM_PATH}. Using fallback elevations.")
        for node in G.nodes():
            G.nodes[node]['elevation'] = 900.0
            G.nodes[node]['elevation_unknown'] = True
        return

    try:
        print(f"Loading elevations from {DEM_PATH}...")
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
        print("Elevations successfully loaded.")
    except Exception as e:
        print(f"Error loading DEM: {e}")
        for node in G.nodes():
            G.nodes[node]['elevation'] = 900.0
            G.nodes[node]['elevation_unknown'] = True

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
