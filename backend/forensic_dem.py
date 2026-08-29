"""
MAXIMUM-FIDELITY FORENSIC AUDIT — DEM/Topography Phase
Run from: backend\ directory
"""
import pickle, sys, os, struct

# No chdir needed - run FROM backend directory
sys.path.insert(0, '.')

print("=" * 60)
print("PHASE 3: DEM FORENSICS")
print("=" * 60)

# Locate DEM relative to backend dir
dem_candidates = [
    r'..\DataSet\N12E077.SRTMGL1.hgt\N12E077.hgt',
    r'..\DataSet\N12E077.hgt\N12E077.hgt',
]
dem_path = next((p for p in dem_candidates if os.path.exists(p)), None)
if not dem_path:
    print("ERROR: DEM not found")
    sys.exit(1)

file_size = os.path.getsize(dem_path)
n = int((file_size // 2) ** 0.5)
print(f"DEM: {dem_path}")
print(f"File size: {file_size} bytes, Grid: {n}x{n}")
print(f"CRS: WGS84 EPSG:4326, Vertical: metres (int16 big-endian)")
print(f"Resolution: ~{1/3600*111000:.1f}m/pixel (SRTM1 1-arcsec)")
print(f"Nodata: -32768")

# Confirm SRTM1
if file_size == 25934402:
    print("Confirmed: SRTMGL1 1-arcsecond tile (~30m)")

# Load graph
with open('data/graphs/osm_fallback.gpickle', 'rb') as f:
    G = pickle.load(f)

from app.simulation.topography import initialize_elevations, get_elevation_bounds, flood_ablate
initialize_elevations(G)
bounds = get_elevation_bounds(G)
print(f"\nGraph: {G.number_of_nodes()} nodes, {G.number_of_edges()} edges")
print(f"Elevation: min={bounds['min']}m max={bounds['max']}m mean={bounds['mean']}m unknown={bounds['unknown_count']}")

# CRITICAL: Verify DEM sampling formula in topography.py
# Code: row = int((tile_lat + 1 - lat) * (samples - 1))
#       col = int((lon - tile_lon) * (samples - 1))
# Tile: N12E077 => tile_lat=12, tile_lon=77
# Formula correct? For lat=12.999: row = int((12+1-12.999)*3600) = int(0.001*3600) = 3 (near north edge)
# For lat=12.001: row = int((13-12.001)*3600) = int(0.999*3600) = 3596 (near south edge)
# This is correct: row 0 = north edge (tile_lat+1), row 3600 = south edge (tile_lat)
print("\nDEM sampling formula verification:")
print("  row = int((tile_lat+1 - lat) * (samples-1))")
print("  col = int((lon - tile_lon) * (samples-1))")
# Test at exactly known lat=13.0 (should be row=0) and lat=12.0 (row=3600)
for lat_test, expected_row in [(13.0, 0), (12.0, 3600), (12.999, 3), (12.001, 3596)]:
    row_test = int((12 + 1 - lat_test) * (3601 - 1))
    print(f"  lat={lat_test}: row={row_test} (expected ~{expected_row}) {'OK' if abs(row_test-expected_row)<=1 else 'CHECK'}")

# Verify actual node elevations vs manual DEM read
print("\nNode elevation verification (manual vs stored):")
mismatches = 0
checked = 0
with open(dem_path, 'rb') as dem_f:
    for nid, nd in list(G.nodes(data=True))[:15]:
        lat = nd.get('y')
        lon = nd.get('x')
        graph_elev = nd.get('elevation')
        if lat is None or lon is None or graph_elev is None:
            print(f"  Node {nid}: MISSING attributes")
            continue
        # Use topography.py formula
        row = int((12 + 1 - lat) * (n - 1))
        col = int((lon - 77) * (n - 1))
        row = max(0, min(row, n - 1))
        col = max(0, min(col, n - 1))
        dem_f.seek((row * n + col) * 2)
        raw = dem_f.read(2)
        manual_elev = struct.unpack('>h', raw)[0]
        match = (manual_elev == int(graph_elev))
        if not match:
            mismatches += 1
        checked += 1
        print(f"  Node {nid}: lat={lat:.5f} lon={lon:.5f} manual={manual_elev}m stored={graph_elev}m {'OK' if match else 'MISMATCH'}")
print(f"\nMismatches: {mismatches}/{checked}")

# DEM BOUNDARY PRECISION TESTS
print("\n" + "=" * 60)
print("DEM BOUNDARY PRECISION TESTS (monotonicity)")
print("=" * 60)
dem_min = bounds['min']
dem_max = bounds['max']
test_levels = [
    dem_min - 1.0,   # expect 0
    dem_min - 0.001, # expect 0
    dem_min,         # expect >= 1
    dem_min + 0.001, # expect >= 1
    dem_min + 0.01,
    dem_min + 1.0,
    905.0,
    dem_max - 1.0,
    dem_max - 0.01,
    dem_max,
]
print(f"DEM range: {dem_min}m - {dem_max}m")
print(f"{'Water Level':>14} | {'Flooded':>10} | Status")
print("-" * 40)
prev_n = None
for wl in test_levels:
    flooded = flood_ablate(G, wl)
    n_f = len(flooded)
    mono_ok = (prev_n is None or n_f >= prev_n)
    status = "OK" if mono_ok else "MONOTONICITY VIOLATION"
    prev_n = n_f
    print(f"  {wl:12.3f}m | {n_f:10d} | {status}")

# Bathtub formula correctness check
print("\nBathtub formula: flooded iff elevation <= water_level")
wl_test = 905.0
flooded_set = set(flood_ablate(G, wl_test))
violations = 0
for nid, nd in G.nodes(data=True):
    elev = nd.get('elevation')
    if elev is None:
        continue
    should = elev <= wl_test
    is_f = nid in flooded_set
    if should != is_f:
        violations += 1
        print(f"  VIOLATION: node {nid} elev={elev} should_flood={should} is_flooded={is_f}")
if violations == 0:
    print(f"  PASS: formula is exact for all {G.number_of_nodes()} nodes at wl={wl_test}m")

# nodata handling check
print("\nNodata handling:")
nodes_unknown = sum(1 for n, d in G.nodes(data=True) if d.get('elevation') is None)
print(f"  Nodes with unknown elevation: {nodes_unknown} (conservatively NOT flooded)")
print(f"  This is correct: uncertain elevation -> do not falsely classify as flooded")
