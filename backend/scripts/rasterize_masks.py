#!/usr/bin/env python3
"""
Rasterize SpaceNet GeoJSON road centerlines into binary PNG masks.
Uses rasterio and shapely to project geographic coordinates to pixel space.
"""
import os
import glob
import json
import numpy as np
import rasterio
from rasterio.features import rasterize
from shapely.geometry import shape
from PIL import Image

def main():
    image_dir = "data/spacenet_roads/images"
    mask_dir = "data/spacenet_roads/masks"

    # Map img{N} suffix to geojson files
    geojson_files = glob.glob(os.path.join(mask_dir, "*.geojson"))
    geojson_map = {}
    for gpath in geojson_files:
        filename = os.path.basename(gpath)
        parts = filename.split("_")
        img_num = parts[-1].replace(".geojson", "") # e.g. "img1"
        geojson_map[img_num] = gpath

    # Map img{N} suffix to tiff files
    tif_files = glob.glob(os.path.join(image_dir, "*.tif"))
    print(f"Found {len(tif_files)} GeoTIFF images.")
    print(f"Found {len(geojson_files)} GeoJSON files.")

    converted_count = 0
    for tpath in tif_files:
        filename = os.path.basename(tpath)
        stem = filename.replace(".tif", "")
        parts = stem.split("_")
        img_num = parts[-1] # e.g. "img1"
        
        gpath = geojson_map.get(img_num)
        if not gpath:
            continue
        
        mask_png_path = os.path.join(mask_dir, f"{stem}.png")
        
        try:
            # Open TIFF to read geographical bounds and pixel dimensions
            with rasterio.open(tpath) as src:
                transform = src.transform
                width = src.width
                height = src.height
                
            # Read GeoJSON vector paths
            with open(gpath, "r", encoding="utf-8") as f:
                geojson_data = json.load(f)
                
            features = geojson_data.get("features", [])
            geoms = []
            for feat in features:
                geom = feat.get("geometry")
                if geom:
                    sh = shape(geom)
                    geoms.append(sh)
                    
            if geoms:
                # Buffer road centerlines by ~3 meters (approx 0.00003 degrees)
                # to render them with realistic road width in pixel space
                buffered_geoms = [g.buffer(0.00003) for g in geoms]
                
                mask = rasterize(
                    [(g, 255) for g in buffered_geoms],
                    out_shape=(height, width),
                    transform=transform,
                    fill=0,
                    all_touched=True,
                    dtype=np.uint8
                )
            else:
                mask = np.zeros((height, width), dtype=np.uint8)
                
            # Save as grayscale PNG
            Image.fromarray(mask).save(mask_png_path)
            converted_count += 1
            
        except Exception as e:
            print(f"Error processing {stem}: {e}")

    print(f"Successfully converted {converted_count} GeoJSON files into PNG masks.")

if __name__ == "__main__":
    main()
