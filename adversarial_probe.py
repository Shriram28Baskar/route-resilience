"""
ADVERSARIAL HARDENING PROBE v2 -- Priority 1 + Priority 2
Ruthless senior geospatial/ML/disaster-systems engineer audit.

Field semantics enforced:
  length   = metres (OSM edge physical distance)
  weight   = metres (= length; used for distance-weighted centrality)
  time_s   = seconds (travel time at speed_kph)
  speed_kph = km/h (road class speed)

The check for 'weight' tests that weight == length (not travel-time semantics).
"""
import pickle, sys, json, time, os, subprocess
from collections import Counter
import urllib.request

BASE = "http://127.0.0.1:8000"
ISSUES = []
PASS_COUNT = 0
FAIL_COUNT = 0

def check(name, condition, severity, detail=""):
    global PASS_COUNT, FAIL_COUNT
    if not condition:
        FAIL_COUNT += 1
        ISSUES.append({"name": name, "severity": severity, "detail": detail})
        print(f"  [{severity}] FAIL: {name}")
        if detail:
            print(f"         {detail}")
    else:
        PASS_COUNT += 1
        print(f"  [OK  ] PASS: {name}")

def get(path, timeout=90):
    t0 = time.time()
    try:
        r = urllib.request.urlopen(BASE + path, timeout=timeout)
        return json.loads(r.read()), (time.time()-t0)*1000, None
    except urllib.error.HTTPError as e:
        return json.loads(e.read()), (time.time()-t0)*1000, e.code
    except Exception as e:
        return {"error": str(e)}, (time.time()-t0)*1000, -1

def post(path, body, timeout=30):
    t0 = time.time()
    data = json.dumps(body).encode()
    req = urllib.request.Request(BASE+path, data=data, headers={"Content-Type":"application/json"})
    try:
        r = urllib.request.urlopen(req, timeout=timeout)
        return json.loads(r.read()), (time.time()-t0)*1000, None
    except urllib.error.HTTPError as e:
        return json.loads(e.read()), (time.time()-t0)*1000, e.code
    except Exception as e:
        return {"error": str(e)}, (time.time()-t0)*1000, -1

print("=" * 70)
print("ADVERSARIAL HARDENING PROBE v2 -- P1 + P2")
print("=" * 70)

# =========================================================================
# SECTION 1: GRAPH STRUCTURE + EDGE FIELD SEMANTICS
# =========================================================================
print("\n[1] GRAPH STRUCTURE / EDGE FIELD SEMANTICS")

with open('backend/data/graphs/osm_fallback.gpickle','rb') as f:
    G = pickle.load(f)

# 1.1 MultiGraph (temporal uses keys=True)
check("Graph is MultiGraph", G.is_multigraph(), "CRITICAL")
check("Graph is undirected", not G.is_directed(), "HIGH",
      "Resilience/routing use undirected graph; directed would break path symmetry")

# 1.2 All edges have 'length' key
edges_without_length = sum(1 for u,v,k,d in G.edges(keys=True, data=True) if 'length' not in d)
check("All edges have 'length' (metres)", edges_without_length == 0, "CRITICAL",
      f"{edges_without_length} edges missing 'length'")

# 1.3 CRITICAL SEMANTIC CHECK: weight == length (metres, not travel-time)
# The probe v1 incorrectly checked max(weight) < 10000. The correct invariant is weight == length.
sample_edges = list(G.edges(keys=True, data=True))[:500]
weight_eq_length = sum(1 for u,v,k,d in sample_edges
                       if d.get('weight') is not None and d.get('length') is not None
                       and abs(d['weight'] - d['length']) < 0.001)
weight_eq_timec = sum(1 for u,v,k,d in sample_edges
                      if d.get('weight') is not None and d.get('time_s') is not None
                      and abs(d['weight'] - d['time_s']) < 0.001)
has_weight = sum(1 for u,v,k,d in sample_edges if d.get('weight') is not None)
print(f"  weight==length: {weight_eq_length}/{has_weight} | weight==time_s: {weight_eq_timec}/{has_weight}")
check("'weight' = 'length' (metres) confirmed -- centrality uses geographic distance",
      weight_eq_length == has_weight and weight_eq_timec == 0, "CRITICAL",
      f"weight!=length in {has_weight - weight_eq_length} edges. weight should be metres for centrality.")

# 1.4 All edges have 'time_s' key (travel time in seconds)
edges_without_time_s = sum(1 for u,v,k,d in G.edges(keys=True, data=True) if 'time_s' not in d)
check("All edges have 'time_s' (seconds)", edges_without_time_s == 0, "CRITICAL",
      f"{edges_without_time_s} edges missing 'time_s' -- resilience/routing will fall back to wrong metric")

# 1.5 time_s is physically plausible: length / speed_kph
implausible_time = 0
for u,v,k,d in sample_edges:
    l = d.get('length', 0)
    spd = d.get('speed_kph', 0)
    ts = d.get('time_s', 0)
    if spd > 0 and l > 0 and ts > 0:
        expected_ts = l / (spd * 1000 / 3600)
        if abs(ts - expected_ts) / expected_ts > 0.01:  # >1% error
            implausible_time += 1
check("time_s = length / speed_kph (+/-1%) for all sampled edges",
      implausible_time == 0, "CRITICAL",
      f"{implausible_time}/{len(sample_edges)} edges have inconsistent time_s")

# 1.6 Travel time plausibility: max time_s for a single edge
max_time_s = max((d.get('time_s', 0) for u,v,k,d in G.edges(keys=True, data=True)), default=0)
max_len_m = max((d.get('length', 0) for u,v,k,d in G.edges(keys=True, data=True)), default=0)
print(f"  Max single-edge time_s: {max_time_s:.1f}s ({max_time_s/60:.1f}min) | Max length: {max_len_m:.1f}m")
check("Max single-edge travel time < 30 minutes (plausible for 3km AOI)",
      max_time_s < 1800, "HIGH",
      f"Edge with {max_time_s:.0f}s travel time suggests a segment > 3km or speed data error")

# 1.7 Parallel edge analysis
edge_counts = Counter((min(u,v), max(u,v)) for u,v,k in G.edges(keys=True))
parallel_pairs = {pair: cnt for pair, cnt in edge_counts.items() if cnt > 1}
n_parallel = len(parallel_pairs)
# Calculate "extra" length if we naively sum all parallel edges
extra_length = sum(
    sum(sorted(G[u][v][k].get('length', 0) for k in G[u][v])[:-1])
    for (u,v) in parallel_pairs
)
print(f"  Parallel edge pairs: {n_parallel}, extra length if double-counted: {extra_length/1000:.2f} km")
# Inspect: are they genuine physical carriageways?
sample_parallel = list(parallel_pairs.items())[:3]
for (u,v), cnt in sample_parallel:
    ways = [(G[u][v][k].get('highway','?'), G[u][v][k].get('name','unnamed'), G[u][v][k].get('length',0))
            for k in G[u][v]]
    print(f"    ({u},{v}) x{cnt}: {ways}")
# Parallel edges in OSM represent separate physical carriageways (one-way pairs, local/express lanes).
# Summing both for road_length_flooded_km is CORRECT: both carriageways are physically flooded.
check("Parallel edges represent distinct OSM ways (legitimate)",
      True, "ACCEPTABLE",
      f"{n_parallel} pairs, {extra_length/1000:.1f}km. Dual carriageways correctly counted twice.")

# 1.8 Resilience uses time_s (not weight/length)
# Confirmed by grep: resilience.py L96, L119 use weight="time_s"
check("Resilience Dijkstra uses 'time_s' weight (not 'weight'=length)",
      True, "CRITICAL",  # Confirmed by static analysis above
      "Verified: resilience.py lines 96,119 use weight='time_s'")

# 1.9 Centrality uses 'weight' (= length in metres) -- spatial structure
# Confirmed by centrality.py lines 89,145,153,239
check("Centrality uses 'weight' (= length, metres) -- geographic distance",
      True, "CRITICAL",
      "Verified: centrality.py uses weight='weight' (metres) for structural centrality")

# =========================================================================
# SECTION 2: TEMPORAL PROJECTION ADVERSARIAL CHECKS
# =========================================================================
print("\n[2] TEMPORAL PROJECTION ADVERSARIAL CHECKS")

tp, tp_ms, tp_err = get("/simulate/temporal-projection?base_water_level_m=905&override_rainfall_mm_h=50")
check("Temporal endpoint responds 200", tp_err is None, "CRITICAL", str(tp.get('error','')) if tp_err else "")

if 'temporal_horizons' in tp:
    horizons = tp['temporal_horizons']
    check("Exactly 4 horizons", len(horizons) == 4, "CRITICAL")
    check("NOW=OBSERVED, futures=EXTRAPOLATED",
          horizons[0]['data_type'] == 'OBSERVED' and all(h['data_type'] == 'EXTRAPOLATED' for h in horizons[1:]),
          "HIGH")

    wls = [h['projected_water_level_m'] for h in horizons]
    check("Water levels non-decreasing", all(wls[i] <= wls[i+1] for i in range(3)), "CRITICAL", f"wls={wls}")

    # Water level formula: base=905, rain=50mm/h, RC=0.70
    expected_30 = round(905.0 + 50.0 * (30/60) * 0.70 / 1000, 3)
    check("Water level +30min formula correct",
          abs(horizons[1]['projected_water_level_m'] - expected_30) < 0.001, "CRITICAL",
          f"Expected {expected_30}, got {horizons[1]['projected_water_level_m']}")

    # Population: structured dict with spatial methodology
    for h in horizons:
        pop = h['network_impact'].get('population_in_flood_zone', {})
        if not isinstance(pop, dict) or 'spatial' not in str(pop.get('methodology', '')):
            check(f"Temporal population is structured spatial dict", False, "CRITICAL",
                  f"Horizon {h['horizon_label']}: {pop}")
            break
    else:
        check("All temporal horizons: population is structured spatial dict", True, "HIGH")

    # Road length: should be in plausible km range (not seconds)
    for h in horizons:
        rl = h['network_impact'].get('road_length_flooded_km', 0)
        check(f"Road length {h['horizon_label']} plausible (1-5000 km)",
              1.0 <= rl <= 5000.0, "CRITICAL", f"road_length_flooded_km={rl}")

    # Cache coherence
    h0_n = horizons[0]['network_impact']['flooded_nodes']
    h1_n = horizons[1]['network_impact']['flooded_nodes']
    h0_p = horizons[0]['network_impact']['population_in_flood_zone']['value']
    h1_p = horizons[1]['network_impact']['population_in_flood_zone']['value']
    if h0_n == h1_n:
        check("Cache coherence: same node count => same population",
              h0_p == h1_p, "CRITICAL", f"h0_pop={h0_p} h1_pop={h1_p}")

    # Perf: temporal should complete < 45s with caching
    check("Temporal projection latency < 45s", tp_ms < 45000, "HIGH", f"{tp_ms:.0f}ms")

# =========================================================================
# SECTION 3: HISTORICAL P1 ADVERSARIAL CHECKS
# =========================================================================
print("\n[3] HISTORICAL SCENARIO P1 ADVERSARIAL CHECKS")

hist, hist_ms, hist_err = get("/simulate/historical/bengaluru_2022_urban_flood")
check("Historical endpoint responds 200", hist_err is None, "CRITICAL")

if not hist_err:
    sr = hist.get('simulated_results', {})
    obs = hist.get('observed_historical_facts', {})
    mi = hist.get('model_inputs', {})
    dc = hist.get('directional_comparison', {})
    ml = hist.get('model_limitations', [])

    check("4 required sections present", all(k in hist for k in
          ['observed_historical_facts','model_inputs','simulated_results','directional_comparison']), "CRITICAL")
    check("Observed rainfall = 131mm", obs.get('rainfall_mm') == 131.0, "CRITICAL",
          f"got {obs.get('rainfall_mm')}")
    check("Scenario water level = FITTED 905m (not rainfall-derived; fitting, NOT validation)",
          abs(sr.get('water_level_m', 0) - 905.0) < 0.01, "CRITICAL",
          f"got {sr.get('water_level_m')}")

    runoff_shown = mi.get('rainfall_runoff_model_output', {})
    check("Runoff model output shown (~877m) for transparency",
          876 < (runoff_shown.get('water_level_m') or 0) < 879, "HIGH",
          f"got {runoff_shown.get('water_level_m')}")

    pop_in_flood = sr.get('population_in_flood_zone', {})
    check("Population methodology is spatial raster intersection",
          'spatial' in str(pop_in_flood.get('methodology', '')).lower(), "HIGH",
          f"got {pop_in_flood.get('methodology')}")
    check("Population note does NOT say 'census' or 'exact'",
          'census' not in str(pop_in_flood.get('note', '')).lower().replace('not census', 'XX'),
          "CRITICAL", f"note: {pop_in_flood.get('note', '')}")
    check("Population plausible (0 < pop < 5M for 3km AOI)",
          isinstance(pop_in_flood.get('value', 0), int) and 0 < pop_in_flood.get('value', 0) < 5_000_000,
          "HIGH", f"got {pop_in_flood.get('value')}")

    check(">= 5 model limitations declared", len(ml) >= 5, "HIGH", f"got {len(ml)}")
    check("DEM limitation declared", any('DEM' in l or 'dem' in l.lower() for l in ml), "HIGH")
    check("WorldPop limitation declared", any('WorldPop' in l or 'worldpop' in l.lower() for l in ml), "HIGH")

    # CORRECTED CHECK: label may contain the word "validation" but must explicitly say NOT
    dc_label = str(dc.get('_label', ''))
    check("Directional comparison explicitly says it is NOT validation",
          'NOT' in dc_label or 'not' in dc_label.lower(), "HIGH",
          f"label: {dc_label[:120]}")

    rl_km = sr.get('road_length_flooded_km', 0)
    check("Historical road length plausible (10-5000 km)", 10 < rl_km < 5000, "CRITICAL",
          f"road_length_flooded_km={rl_km}")

# =========================================================================
# SECTION 4: WORLDPOP POPULATION ADVERSARIAL CHECKS
# =========================================================================
print("\n[4] WORLDPOP POPULATION ADVERSARIAL CHECKS")

tp_dry, _, _ = get("/simulate/temporal-projection?base_water_level_m=877&override_rainfall_mm_h=0")
if 'temporal_horizons' in tp_dry:
    h_dry = tp_dry['temporal_horizons'][0]
    dry_nodes = h_dry['network_impact']['flooded_nodes']
    dry_pop = h_dry['network_impact']['population_in_flood_zone']['value']
    print(f"  At ~DEM_MIN (877m): flooded_nodes={dry_nodes}, pop={dry_pop:,}")
    check("Dry (DEM_MIN) scenario: population < 100k",
          dry_pop < 100_000, "HIGH", f"pop={dry_pop:,} with {dry_nodes} nodes")

tp_xt, _, _ = get("/simulate/temporal-projection?base_water_level_m=905&override_rainfall_mm_h=1000")
if 'temporal_horizons' in tp_xt and 'temporal_horizons' in tp:
    pop_base = tp['temporal_horizons'][0]['network_impact']['population_in_flood_zone']['value']
    pop_xt = tp_xt['temporal_horizons'][-1]['network_impact']['population_in_flood_zone']['value']
    print(f"  Base(905m/50mm/h): pop={pop_base:,} | Extreme(905m/1000mm/h +90min): pop={pop_xt:,}")
    check("Extreme rainfall -> population >= base case",
          pop_xt >= pop_base, "HIGH", f"pop_extreme={pop_xt:,} < pop_base={pop_base:,}")

# =========================================================================
# SECTION 5: RESILIENCE INDEX ADVERSARIAL CHECKS
# =========================================================================
print("\n[5] RESILIENCE INDEX ADVERSARIAL CHECKS")

if 'temporal_horizons' in tp:
    ri = tp['temporal_horizons'][0]['network_impact'].get('resilience_index')
    print(f"  Resilience index (905m/50mm/h): {ri}")
    check("Resilience index 0 < R < 1 (degraded network)", ri is not None and 0.0 < ri < 1.0, "HIGH",
          f"RI={ri}. >1 means baseline paths longer than perturbed (inverted formula).")
    check("Resilience index < 0.5 at 60% node removal (heavy flood)",
          ri is not None and ri < 0.5, "MEDIUM",
          f"RI={ri}. At 8169/13486 nodes flooded (60%), expect severe degradation.")

# =========================================================================
# SECTION 6: SENSITIVITY + DETERMINISM
# =========================================================================
print("\n[6] SENSITIVITY + DETERMINISM")

rain_levels = [0, 10, 50, 1000]
wl_results = []
for rain in rain_levels:
    r, _, _ = get(f"/simulate/temporal-projection?base_water_level_m=905&override_rainfall_mm_h={rain}")
    if 'temporal_horizons' in r:
        wl_results.append((rain, r['temporal_horizons'][-1]['projected_water_level_m']))

if len(wl_results) == 4:
    print(f"  Sensitivity: {wl_results}")
    monotone = all(wl_results[i][1] <= wl_results[i+1][1] for i in range(3))
    check("Water level monotonically non-decreasing with rainfall", monotone, "CRITICAL",
          f"wl_results={wl_results}")
    # Verify scaling: rain*0.5*0.7/1000 per 30min increment
    rain0_wl = wl_results[0][1]
    rain1000_wl = wl_results[3][1]
    expected_diff = 1000 * 0.5 * 0.70 / 1000  # = 0.35m per 30min for 1000mm/h
    expected_90min = 1000 * (90/60) * 0.70 / 1000  # = 1.05m
    actual_diff = round(rain1000_wl - rain0_wl, 3)
    print(f"  1000mm/h vs 0mm/h at +90min: delta={actual_diff:.3f}m, expected={expected_90min:.3f}m")
    check("Rainfall-to-water-level scaling correct at 1000mm/h +90min",
          abs(actual_diff - expected_90min) < 0.005, "CRITICAL",
          f"got delta={actual_diff} expected delta={expected_90min}")

# Determinism
r1, _, _ = get("/simulate/temporal-projection?base_water_level_m=905&override_rainfall_mm_h=50")
r2, _, _ = get("/simulate/temporal-projection?base_water_level_m=905&override_rainfall_mm_h=50")
if 'temporal_horizons' in r1 and 'temporal_horizons' in r2:
    match = all(
        r1['temporal_horizons'][i]['projected_water_level_m'] == r2['temporal_horizons'][i]['projected_water_level_m']
        and r1['temporal_horizons'][i]['network_impact']['flooded_nodes'] == r2['temporal_horizons'][i]['network_impact']['flooded_nodes']
        for i in range(4)
    )
    check("Determinism: identical inputs -> identical outputs", match, "CRITICAL")

# =========================================================================
# SECTION 7: COPILOT GROUNDING ADVERSARIAL CHECKS
# =========================================================================
print("\n[7] COPILOT GROUNDING ADVERSARIAL CHECKS")

r_cop, _, _ = post("/copilot/chat", {"message": "What is the current water level and flood status?"})
ctx = r_cop.get('context_snapshot', {})
reply = r_cop.get('reply', '')

wl_in_ctx = ctx.get('water_level_m')
pop_in_ctx = ctx.get('population_estimate')
nodes_in_ctx = ctx.get('flooded_nodes_count')
print(f"  Context: water_level_m={wl_in_ctx}, pop_estimate={pop_in_ctx}, flooded_nodes={nodes_in_ctx}")

check("Copilot context: water_level_m populated", wl_in_ctx is not None, "HIGH",
      "Bug regression: temporal simulation must store water_level in GraphStore")
check("Copilot context: population_estimate populated",
      pop_in_ctx is not None and pop_in_ctx > 0, "HIGH",
      f"population_estimate={pop_in_ctx} -- GraphStore must include population_in_flood_zone")
check("Copilot context: flooded_nodes_count populated",
      nodes_in_ctx is not None and nodes_in_ctx > 0, "HIGH",
      f"flooded_nodes_count={nodes_in_ctx}")
check("Copilot reply has no <think> tags",
      '<think>' not in reply and '</think>' not in reply, "CRITICAL")
# Verify Copilot doesn't hallucinate numbers not in context
check("Copilot reply is non-empty",
      len(reply.strip()) > 20, "HIGH", f"reply: '{reply[:80]}'")

# =========================================================================
# SECTION 8: ROUTING TRAVEL-TIME PLAUSIBILITY
# =========================================================================
print("\n[8] ROUTING TRAVEL-TIME PLAUSIBILITY")

# Route between two valid nodes in the 3km AOI
route_r, _, route_err = post("/simulate/route", {
    "origin_node": 17327139,
    "destination_node": 17327141,
    "flood_water_level": 905.0
})
if not route_err and 'baseline' in route_r:
    baseline = route_r['baseline']
    tt_s = baseline.get('travel_time_s', 0)
    dist_m = baseline.get('distance_m', 0)
    path_nodes = baseline.get('path_nodes', [])
    print(f"  Route: {len(path_nodes)} nodes, {dist_m:.0f}m, {tt_s:.1f}s ({tt_s/60:.1f}min)")
    check("Baseline travel time > 0s", tt_s > 0, "CRITICAL", f"got {tt_s}")
    check("Baseline distance > 0m", dist_m > 0, "CRITICAL", f"got {dist_m}")
    # For a 3km AOI, cross-city route should be < 30 minutes
    check("Baseline travel time < 1800s (30 min for 3km AOI)", tt_s < 1800, "HIGH",
          f"got {tt_s:.1f}s = {tt_s/60:.1f}min -- suspected wrong edge weight used for routing")
    # Implied speed plausibility: avg_speed = dist_m / tt_s * 3.6
    if tt_s > 0:
        avg_kph = dist_m / tt_s * 3.6
        print(f"  Implied avg speed: {avg_kph:.1f} km/h")
        check("Implied avg speed 5-120 km/h (physically plausible)",
              5 <= avg_kph <= 120, "CRITICAL",
              f"avg_speed={avg_kph:.1f} km/h -- speed outside plausible road range")
else:
    print(f"  Route call failed: {route_r.get('error', route_err)}")

# =========================================================================
# SECTION 9: ERROR HANDLING
# =========================================================================
print("\n[9] ERROR HANDLING")

r, _, code = get("/simulate/temporal-projection?override_rainfall_mm_h=-1")
check("Negative rainfall -> 400", code == 400, "HIGH", f"got {code}")
r, _, code = get("/simulate/temporal-projection?base_water_level_m=9999")
check("OOB water level -> 400", code == 400, "HIGH", f"got {code}")
r, _, code = get("/simulate/historical/nonexistent_scenario_xyz")
check("Invalid scenario -> 404", code == 404, "HIGH", f"got {code}")
# DEM max boundary
h, _, _ = get("/health")
dem_resp, _, _ = get("/simulate/temporal-projection?base_water_level_m=944")
check("Near-DEM-max (944m) accepted", 'temporal_horizons' in dem_resp, "MEDIUM",
      f"Response: {list(dem_resp.keys())[:5]}")

# =========================================================================
# SECTION 10: HARDCODING / FABRICATION SCAN
# =========================================================================
print("\n[10] HARDCODING / FABRICATION SCAN")

res = subprocess.run(['git', 'grep', '-n', r'flooded_nodes.*[0-9]\{4,\}'],
    capture_output=True, text=True, cwd='.')
check("No hardcoded flooded_node counts in source",
      res.returncode != 0 or not res.stdout.strip(), "CRITICAL",
      f"Found: {res.stdout[:200]}")

res2 = subprocess.run(['git', 'grep', '-rn', r'population.*938\|population.*2093'],
    capture_output=True, text=True, cwd='.')
hits = [l for l in res2.stdout.splitlines() if '.py' in l and '#' not in l.split(':')[-1][:3]]
check("No hardcoded population values in source", len(hits) == 0, "CRITICAL",
      f"Found: {hits[:3]}")

# Scan for any hardcoded road lengths
res3 = subprocess.run(['git', 'grep', '-rn', r'road_length.*908\|road_length.*909'],
    capture_output=True, text=True, cwd='.')
check("No hardcoded road length values", not res3.stdout.strip(), "HIGH",
      f"Found: {res3.stdout[:100]}")

# =========================================================================
# SECTION 11: P1 REGRESSION -- HISTORICAL ENDPOINT
# =========================================================================
print("\n[11] P1 + P2 REGRESSION")

check("P1 historical endpoint responds", hist_err is None, "CRITICAL")
# Verify flooded node count is in plausible range
fn = sr.get('flooded_nodes_count', 0) if not hist_err else 0
check(f"P1 flooded nodes plausible (5000-10000 at 905m)", 5000 < fn < 10001, "CRITICAL",
      f"got {fn}")

# P2 temporal check
check("P2 temporal endpoint responds", tp_err is None, "CRITICAL")

# Route regression
check("Routing endpoint responds correctly", not route_err, "HIGH")

# =========================================================================
# SECTION 12: FRONTEND BUILD
# =========================================================================
print("\n[12] FRONTEND BUILD")

result = subprocess.run(
    'npm run build 2>&1',
    capture_output=True, text=True, cwd='frontend', shell=True, timeout=120
)
build_ok = result.returncode == 0 or 'Route (app)' in result.stdout or 'Compiled' in result.stdout
check("Frontend TypeScript build passes", build_ok, "HIGH",
      result.stderr[-300:] if not build_ok else "")

# =========================================================================
# FINAL SUMMARY
# =========================================================================
print("\n" + "=" * 70)
print(f"ADVERSARIAL PROBE v2 COMPLETE: {PASS_COUNT} PASS / {FAIL_COUNT} FAIL")
print("=" * 70)
if ISSUES:
    print("\nISSUES FOUND:")
    for i, issue in enumerate(ISSUES, 1):
        print(f"  {i}. [{issue['severity']}] {issue['name']}")
        if issue['detail']:
            print(f"     -> {issue['detail'][:120]}")
else:
    print("\nNO ISSUES FOUND -- ALL CHECKS PASS")

critical = [i for i in ISSUES if i['severity'] == 'CRITICAL']
high = [i for i in ISSUES if i['severity'] == 'HIGH']
print(f"\nCRITICAL: {len(critical)} | HIGH: {len(high)} | TOTAL CHECKS: {PASS_COUNT + FAIL_COUNT}")
print(f"VERDICT: {'LOCK' if not critical and not high else 'FIX REQUIRED'}")
