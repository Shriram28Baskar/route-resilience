"""
Step 1 Diagnostic: Verify DEM, graph and coordinate system alignment.
"""
import os, sys, struct, math, json, random

HGT_FILES = [
    r"C:\Users\Saish\OneDrive\Documents\route-resilience\DataSet\N12E077.SRTMGL1.hgt\N12E077.hgt",
    r"C:\Users\Saish\OneDrive\Documents\route-resilience\DataSet\N12E077.hgt\N12E077.hgt",
]

AOI = {"south": 12.92, "west": 77.57, "north": 12.99, "east": 77.64}

LANDMARKS = [
    {"name": "Lal Bagh",        "lat": 12.9507, "lon": 77.5848, "expected_m": 920},
    {"name": "MG Road",          "lat": 12.9767, "lon": 77.6099, "expected_m": 921},
    {"name": "Cubbon Park",      "lat": 12.9763, "lon": 77.5929, "expected_m": 921},
    {"name": "City Railway Stn", "lat": 12.9784, "lon": 77.5701, "expected_m": 914},
    {"name": "Ulsoor Lake",      "lat": 12.9819, "lon": 77.6204, "expected_m": 916},
]

def parse_hgt_filename(filepath):
    name = os.path.basename(filepath).upper()
    lat_sign = 1 if name[0] == 'N' else -1
    lon_sign = 1 if name[3] == 'E' else -1
    return lat_sign * int(name[1:3]), lon_sign * int(name[4:7])

def get_hgt_resolution(filesize_bytes):
    if filesize_bytes == 2884802: return 1201, "3-arcsec SRTM3 ~90m"
    elif filesize_bytes == 25934402: return 3601, "1-arcsec SRTMGL1 ~30m"
    else:
        s = int(math.sqrt(filesize_bytes / 2))
        return s, f"unknown {s}x{s}"

def read_elevation_hgt(filepath, lat, lon):
    if not os.path.exists(filepath): return None
    filesize = os.path.getsize(filepath)
    samples, _ = get_hgt_resolution(filesize)
    tile_lat, tile_lon = parse_hgt_filename(filepath)
    if not (tile_lat <= lat < tile_lat + 1 and tile_lon <= lon < tile_lon + 1): return None
    row = int((tile_lat + 1 - lat) * (samples - 1))
    col = int((lon - tile_lon) * (samples - 1))
    row = max(0, min(row, samples - 1))
    col = max(0, min(col, samples - 1))
    offset = ((row * samples) + col) * 2
    with open(filepath, "rb") as f:
        f.seek(offset)
        raw = f.read(2)
    if len(raw) < 2: return None
    elev = struct.unpack(">h", raw)[0]
    return elev if elev != -32768 else None

def best_elevation(lat, lon):
    for hgt in HGT_FILES:
        e = read_elevation_hgt(hgt, lat, lon)
        if e is not None: return e, hgt
    return None, None

print("="*60)
print("  STEP 1 — DEM & COORDINATE SYSTEM VERIFICATION")
print("="*60)

print("\n[1] HGT FILES")
valid_hgts = []
for hgt in HGT_FILES:
    if os.path.exists(hgt):
        size = os.path.getsize(hgt)
        samples, desc = get_hgt_resolution(size)
        lat_sw, lon_sw = parse_hgt_filename(hgt)
        print(f"  OK  {os.path.basename(hgt)} | {desc} | covers lat {lat_sw}-{lat_sw+1} lon {lon_sw}-{lon_sw+1}")
        valid_hgts.append(hgt)
    else:
        print(f"  MISSING  {hgt}")

print("\n[2] LANDMARK SPOT-CHECK (expected ~900-950m for Bengaluru plateau)")
print(f"  {'Landmark':<25} {'Measured':>9} {'Expected':>9} {'Delta':>7} Status")
for lm in LANDMARKS:
    elev, src = best_elevation(lm["lat"], lm["lon"])
    if elev is None:
        print(f"  {lm['name']:<25} {'N/A':>9} {lm['expected_m']:>9} {'N/A':>7} NO DATA")
    else:
        delta = elev - lm["expected_m"]
        status = "OK" if abs(delta) <= 30 else "WARN"
        print(f"  {lm['name']:<25} {elev:>9}m {lm['expected_m']:>9}m {delta:>+7}m {status}")

print("\n[3] AOI GRID STATS (10x10 sample)")
elevs = []
for i in range(10):
    for j in range(10):
        lat = AOI['south'] + i*(AOI['north']-AOI['south'])/9
        lon = AOI['west']  + j*(AOI['east'] -AOI['west'] )/9
        e, _ = best_elevation(lat, lon)
        if e and e > 0: elevs.append(e)
if elevs:
    print(f"  Min: {min(elevs)}m  Max: {max(elevs)}m  Mean: {sum(elevs)/len(elevs):.1f}m  Samples: {len(elevs)}/100")
    ok = 800 <= min(elevs) <= 1100 and 800 <= max(elevs) <= 1100
    print(f"  {'OK - Bengaluru plateau range confirmed' if ok else 'WARN - check tile'}")
else:
    print("  ERROR: no valid samples")

print("\n" + "="*60)
print("  Done. If all checks pass, proceed to Step 2.")
print("="*60)
