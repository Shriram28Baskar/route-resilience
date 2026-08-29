"""
download_dem.py - One-shot DEM downloader for Route Resilience.
Downloads SRTM 30m elevation data for Bengaluru AOI.
AOI: 12.85-13.05N, 77.45-77.75E (slightly wider than graph AOI to avoid edge clipping)
Usage: python scripts/download_dem.py
"""
import os, sys, io, zipfile, tempfile, logging, urllib.request

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger(__name__)

AOI_SOUTH, AOI_NORTH, AOI_WEST, AOI_EAST = 12.85, 13.05, 77.45, 77.75
OUTPUT_PATH = "data/rasters/dem.tif"

def download_opentopo():
    url = (
        "https://portal.opentopography.org/API/globaldem"
        f"?demtype=SRTMGL1&south={AOI_SOUTH}&north={AOI_NORTH}"
        f"&west={AOI_WEST}&east={AOI_EAST}&outputFormat=GTiff&API_Key=demoapikeyot2022"
    )
    logger.info(f"Downloading SRTM GL1 from OpenTopography...")
    req = urllib.request.Request(url, headers={"User-Agent": "route-resilience/1.0"})
    with urllib.request.urlopen(req, timeout=120) as resp:
        data = resp.read()
    logger.info(f"Downloaded {len(data):,} bytes.")
    return data

def crop_and_save(raw_bytes, output_path, is_zip=False):
    import rasterio
    from rasterio.windows import from_bounds
    from rasterio.transform import from_bounds as tfb

    os.makedirs(os.path.dirname(output_path), exist_ok=True)

    if is_zip:
        with zipfile.ZipFile(io.BytesIO(raw_bytes)) as zf:
            tif_names = [n for n in zf.namelist() if n.lower().endswith((".tif", ".hgt"))]
            if not tif_names:
                logger.error("No raster file found in ZIP"); sys.exit(1)
            raw_bytes = zf.read(tif_names[0])
            logger.info(f"Extracted {tif_names[0]} from ZIP.")

    with tempfile.NamedTemporaryFile(suffix=".tif", delete=False) as tmp:
        tmp.write(raw_bytes)
        tmp_path = tmp.name

    try:
        with rasterio.open(tmp_path) as src:
            logger.info(f"Source DEM: CRS={src.crs}, shape={src.shape}, bounds={src.bounds}")
            window = from_bounds(AOI_WEST, AOI_SOUTH, AOI_EAST, AOI_NORTH, src.transform)
            data = src.read(1, window=window)
            new_transform = tfb(AOI_WEST, AOI_SOUTH, AOI_EAST, AOI_NORTH, data.shape[1], data.shape[0])
            profile = src.profile.copy()
            profile.update({"height": data.shape[0], "width": data.shape[1], "transform": new_transform, "compress": "lzw"})
            with rasterio.open(output_path, "w", **profile) as dst:
                dst.write(data, 1)
            valid = data[data > -1000]
            if len(valid) > 0:
                logger.info(f"DEM saved to {output_path} | Shape={data.shape} | Elevation: {valid.min():.0f}m - {valid.max():.0f}m")
            else:
                logger.warning("All elevation values are nodata.")
    finally:
        os.unlink(tmp_path)

def main():
    if os.path.exists(OUTPUT_PATH):
        logger.info(f"DEM already exists at {OUTPUT_PATH}. Delete it to re-download.")
        return
    if len(sys.argv) == 3 and sys.argv[1] == "--file":
        logger.info(f"Using local file: {sys.argv[2]}")
        with open(sys.argv[2], "rb") as f: raw = f.read()
        crop_and_save(raw, OUTPUT_PATH, is_zip=sys.argv[2].lower().endswith(".zip"))
        return
    try:
        raw = download_opentopo()
        is_zip = raw[:2] == b"PK"
        crop_and_save(raw, OUTPUT_PATH, is_zip=is_zip)
    except Exception as e:
        logger.error(f"Download failed: {e}")
        logger.error("Manual fallback: download N13E077 SRTM tile from https://dwtkns.com/srtm30m/")
        logger.error("Then run: python scripts/download_dem.py --file /path/to/tile.zip")
        sys.exit(1)

if __name__ == "__main__":
    main()
