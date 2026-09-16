# Data artifacts

**No data ships with this repository.** Every file listed here must be obtained
and placed by hand. Nothing is generated, simulated, or substituted when a file
is missing: endpoints that need it return **HTTP 503** with a `data_provenance`
block naming the artifact.

This is deliberate. A missing input previously produced confident-looking
numbers derived from hardcoded constants, which is indistinguishable from a real
result once it reaches a chart.

## How provenance is reported

Every numeric endpoint returns a `data_provenance` block:

```json
{
  "status": "measured | derived | synthetic | unavailable",
  "inputs": [{"name": "dem", "path": "data/rasters/dem.tif", "present": false, ...}],
  "assumptions": ["population_per_node = 1008 ..."],
  "notes": ["..."]
}
```

| status | meaning |
|---|---|
| `measured` | computed from a real artifact present on disk |
| `derived` | measured input **plus** documented modelling constants that are not themselves measured |
| `synthetic` | placeholder model, no real input backing it |
| `unavailable` | required input missing — endpoint returns 503, never a number |

An endpoint whose `status` is `derived` is still not a measurement. Read the
`assumptions` list before citing any figure.

## Required artifacts

| Artifact | Path | Needed by | How to obtain |
|---|---|---|---|
| OSM road graph | `graphs/osm_fallback.gpickle` | everything | `python scripts/download_data.py` — **works OFFLINE for the default Bengaluru AOI.** A committed Overpass response at `backend/cache/befdaed17dcd4b1967a71e322ded5946f4da89e1.json` (39,264 nodes / 12,135 ways, `timestamp_osm_base` 2026-06-16) is read by OSMnx's own disk cache (`settings.cache_folder = ./cache`) and yields a connected **13,486-node / 19,117-edge** graph with real coordinates. Other AOIs need network access to Overpass. |
| DEM raster | `rasters/dem.tif` | `/simulate/flood`, `/simulate/flood/curve` | Bhuvan CartoDEM or SRTM tile, clipped to the AOI bbox, elevations in metres ASL |
| Vulnerability CSV | `census/vulnerability.csv` | `/simulate/equity-metrics` | Census of India ward tables |
| OD matrix CSV | `census/od_matrix.csv` | `/simulate/traffic-impact` | Household travel survey / BBMP–BMTC OD study |
| Road conditions CSV | `infrastructure/road_conditions.csv` | `/simulate/degradation-forecast` | BBMP road asset register |
| WorldPop CSV | `infrastructure/worldpop_bengaluru.csv` | `/accessibility/equity` | WorldPop or Census ward tables |
| Model checkpoint | `checkpoints/best_model.pth` | `/segment/*` (only when `ENABLE_ML=true`) | train via `app/ml/train.py` |

### Expected schemas

`census/vulnerability.csv`
```
zone_name,lat,lon,population,vulnerability_score
```
`vulnerability_score` in [0,1].

`census/od_matrix.csv`
```
origin_zone,dest_zone,origin_lat,origin_lon,dest_lat,dest_lon,daily_trips
```

`infrastructure/road_conditions.csv`
```
segment_id,zone,road_type,length_km,structural_health_index,degradation_rate_per_year,annual_maintenance_budget_inr
```
`structural_health_index` in [0,1]; `road_type` one of `highway|major_road|minor_road`.

`infrastructure/worldpop_bengaluru.csv`
```
ward_id,ward_name,lat,lon,population_2011,vulnerable_elderly_pct,vulnerable_disabled_pct,below_poverty_line_pct,nearest_hospital_dist_km,risk_level
```

## Which graph is being analysed

`GET /graph/source` reports the exact artifact under analysis: AOI bounding box,
osmnx version, download timestamp, node/edge counts, and a deterministic
**fingerprint**.

The fingerprint is a SHA-256 over the schema version, node IDs, the edge set,
the routing weights (`weight`, `length`, `time_s`, quantised to 6 significant
figures) and the AOI bbox. Coordinates are excluded — centrality does not read
them and float jitter would churn the hash.

Cached centrality (`graphs/osm_fallback_criticality.pickle`) is keyed to that
fingerprint. A cache whose fingerprint does not match the loaded graph is
**refused**:

* default — discarded with a warning, metrics recomputed
* `STRICT_GRAPH_CACHE=true` — raises `StaleCacheError`

Use strict mode in CI and any reproducibility run, where silently recomputing
would hide a provenance error.

> **The criticality pickle committed here is not a result and not a graph.**
>
> `graphs/osm_fallback_criticality.pickle` predates fingerprinting. It carries no
> `graph_fingerprint` key and is therefore **rejected on load**. It holds
> betweenness/closeness scores for 13,486 node IDs and 19,117 edge keys, with no
> record of which AOI, OSMnx version or date produced them. Do not cite it.
>
> **On the "Bengaluru topology proxy."** Development reports in this repository
> reference a 13,486-node graph reconstructed from that pickle's
> *edge-betweenness keys*. To be unambiguous about what that object is:
>
> * it has the **node and edge set** of the original network;
> * it has **no edge lengths, no travel times, no speed limits, no geometry and
>   no coordinates** — all were assigned uniform placeholder values;
> * it is therefore **NOT the Bengaluru road graph**, and no distance-, time- or
>   centrality-weighted result computed on it is a result about Bengaluru.
>
> It was used for exactly one purpose: counting how often the route endpoint
> injected a fabricated failure, which depends on topology alone. Every other
> measurement in those reports was run on the declared synthetic fixtures in
> `backend/tests/conftest.py`. **No measurement on the real Bengaluru road
> network exists in this repository.**

## Reproducing a run

```bash
export AOI_SOUTH=12.9200 AOI_WEST=77.5700 AOI_NORTH=12.9900 AOI_EAST=77.6400
python scripts/download_data.py          # writes graphs/osm_fallback.gpickle
export STRICT_GRAPH_CACHE=true
uvicorn app.main:app --port 8000
curl localhost:8000/graph/source         # record this fingerprint alongside results
```

Quote the fingerprint next to any number you report. Two runs with different
fingerprints are not comparable.


---

## The committed Overpass cache (added after the post-publication audit)

`backend/cache/befdaed17dcd4b1967a71e322ded5946f4da89e1.json` — 6.0 MB,
git-tracked since the initial commit `f015407` — is a genuine Overpass API
response, not a derived artifact:

```
generator            Overpass API 0.7.62.11 87bfad18
timestamp_osm_base   2026-06-16T05:57:09Z
elements             51,399  (39,264 node, 12,135 way)
bbox                 lat 12.90665 .. 12.99830   lon 77.55759 .. 77.65045
highway tags         residential 8076, tertiary 979, secondary 955,
                     primary 925, living_street 711, trunk 65, ...
```

The filename is OSMnx's SHA-1 of the query, and `osmnx.settings.cache_folder`
defaults to `./cache`, so the fetch is served from disk. Verified by building
the graph with `socket.connect` raising:

```
13,486 nodes, 19,117 edges, connected: True, components: 1
sample node: (17327139, {'y': 12.9349653, 'x': 77.6240716, 'street_count': 3})
```

**Two things follow, and one does not.**

1. Every statement in this repository that the OSM extract was "not committed" or
   the graph "unobtainable" was **false**. Those statements have been corrected in
   README.md, CLAIMS.md, RESEARCH_CLOSURE.md, `experiments/POSTMORTEM_H2.md` and
   `experiments/PREREGISTRATION_DEVIATIONS.md` (D9).
2. The withdrawn figures "13,486 intersections" and "16,000+ road segments" are
   reproducible and have been reinstated as descriptions of the graph.
3. **It does NOT follow that any result here is about Bengaluru.** A5 ran on a
   weightless topology proxy; A7 and P2.2 ran on synthetic families. None used this
   graph. Running them on it would be a new experiment, and none has been run.

Before reporting any result against this graph, record its fingerprint via
`GET /graph/source` and quote it alongside the number.
