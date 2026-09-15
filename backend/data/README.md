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
| OSM road graph | `graphs/osm_fallback.gpickle` | everything | `python scripts/download_data.py` (needs Overpass access) |
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

> The criticality pickle currently committed to this repository predates
> fingerprinting. It carries no `graph_fingerprint` key and is therefore
> **rejected on load**. It is retained only as a record of the 13,486-node /
> 19,117-edge network the earlier README figures were computed from. Do not
> cite it as a result.

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
