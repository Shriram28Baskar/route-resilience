"""
Step 3 - WorldPop population module.
Reads population from the WorldPop UN-adjusted constrained 2020 raster.
All numbers returned are directly sourced from pixel values in the raster.
No estimates, no formulas.
"""
import struct, os
import rasterio
from rasterio.mask import mask as rasterio_mask
from shapely.geometry import mapping, box
import numpy as np

WORLDPOP_PATH = r"C:\Users\Saish\OneDrive\Documents\route-resilience\DataSet\ind_ppp_2020_UNadj_constrained.tif"

def query_population_bbox(south: float, west: float, north: float, east: float) -> dict:
    """
    Return the total population within a bounding box from WorldPop 2020.
    source: WorldPop UN-adjusted constrained 2020, India, ~100m resolution.
    """
    if not os.path.exists(WORLDPOP_PATH):
        return {"population": None, "source": "WorldPop file not found", "error": True}
    
    geom = box(west, south, east, north)
    with rasterio.open(WORLDPOP_PATH) as src:
        out_image, out_transform = rasterio_mask(src, [mapping(geom)], crop=True)
        nodata = src.nodata
    
    data = out_image[0]
    valid = data[(data != nodata) & (data > 0)] if nodata is not None else data[data > 0]
    total = float(np.sum(valid))
    return {
        "population": round(total),
        "source": "WorldPop_2020_UNadj_constrained_100m",
        "pixel_count": int(valid.size),
        "error": False
    }

# Test: query for Bengaluru AOI
result = query_population_bbox(12.92, 77.57, 12.99, 77.64)
print(result)
