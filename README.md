# Route Resilience

![Python 3.11](https://img.shields.io/badge/Python-3.11-blue.svg) ![FastAPI](https://img.shields.io/badge/FastAPI-005571?style=flat&logo=fastapi) ![Next.js](https://img.shields.io/badge/Next.js-black?style=flat&logo=next.js) ![Docker](https://img.shields.io/badge/Docker-2496ED?style=flat&logo=docker) ![ISRO Hackathon 2026](https://img.shields.io/badge/ISRO_Hackathon-2026-orange.svg)

**Occlusion-Robust Road Extraction & Graph-Theoretic Criticality Analysis for Urban Mobility**

Built for ISRO NNRMS — Problem Statement PS4 | 30-hour hackathon

> Which road junctions, if closed, would fragment a city's road network the most —
> and does building a specific link actually prevent that fragmentation?
>
> **Status: research prototype. No validated results yet.** See
> [Claim status](#claim-status) before citing any number from this repository.

---

## Table of Contents
- [Why Route Resilience Matters](#why-route-resilience-matters)
- [Architecture](#architecture)
- [Novel Contributions](#novel-contributions)
- [ISRO & NDMA Integration](#isro--ndma-integration)
- [Claim status](#claim-status)
- [Feature Coverage](#feature-coverage)
- [Known Limitations](#known-limitations)
- [Quick Start](#quick-start)
- [Tech Stack](#tech-stack)
- [Author](#Author)

---

## Why Route Resilience Matters

Most road extraction systems stop after mapping roads. Route Resilience answers:
- Which roads matter most?
- What happens if they fail?
- How do failures propagate?
- Which populations are affected?
- Which intervention prevents collapse?

The graph-analysis half of that is implemented and tested. The satellite-imagery
half runs but has no trained model committed, and its output is deliberately kept
out of the analysis path (see [Known Limitations](#known-limitations)).

---

## Architecture

```text
Satellite Imagery
       ↓
Road Extraction Model
       ↓
Road Graph Generation
       ↓
Critical Junction Detection
       ↓
Disaster Simulation Engine
       ↓
Counterfactual Intervention Validation
       ↓
AI Copilot + Dashboard
```

### Directory Structure
```
route-resilience/
├── backend/          Python FastAPI — graph pipeline, simulation, optional ML
├── frontend/         Next.js 14 — interactive dashboard, Leaflet map, Copilot chat
├── notebooks/        Jupyter — data exploration, model evaluation, validation
└── docker-compose.yml
```

## Novel Contributions

The only contribution here that is both implemented and not standard practice is:

**Counterfactual intervention validation** — propose a link, add it to the
*baseline* graph, re-run the *identical* stressor, and report the measured
change, including when the intervention does not help. `/simulate/ablate/prescribe`,
tested in `tests/test_no_clamps.py`.

The rest is engineering integration of established methods (Brandes betweenness,
articulation points, percolation curves, Dijkstra with edge-penalised
alternatives, U-Net segmentation, LLM-over-context chat). Link addition for
network robustness has substantial prior art; the algorithm is not novel. What
would be novel is an evaluation protocol validated against a real disaster —
**which does not yet exist in this repository.**

Previously listed as novel contributions but not delivered: capacity-constrained
evacuation planning (not implemented), dynamic flood impact modelling (bathtub
threshold, no hydrology), occlusion robustness (augmentations exist, the
measurement does not).

---

## ISRO & NDMA Integration

Intended alignment with ISRO NNRMS and NDMA protocols. Current implementation status:

* **Bhuvan tile integration** — Leaflet layer configuration for Bhuvan WMS endpoints exists in `app/integrations/bhuvan.py`. The layer names have **not been verified against the live service**, and no request has been made from this environment.
* **Change detection** — the module is a stub (see feature table). Sentinel-2 / ResourceSat ingestion is not implemented.
* **Sendai Priority 4 evacuation** — **not implemented.** `/simulate/evacuate` returns 503.

These are design intentions, not delivered capabilities.

## Claim status

**Every previously published benchmark in this README has been withdrawn.** None
could be regenerated from code or data in this repository.

| Withdrawn claim | Why it was removed |
|---|---|
| IoU 0.73, F1 0.81 on SpaceNet Roads | No trained checkpoint, no SpaceNet data, and no evaluation script exist in this repo. Unreproducible. |
| "+12% IoU retention at 40% occlusion" | No occlusion benchmark is implemented. The augmentation pipeline exists; the measurement does not. |
| Precision@5 = 4/5, Precision@10 = 8/10 vs Chennai 2015 / Kerala 2018 | `notebooks/04_validation.ipynb` contains one markdown cell and zero code. No ground-truth file exists. |
| "13,486 intersections, 16,000+ road segments" | Taken from a cached centrality pickle that predates graph fingerprinting and is now rejected on load. The OSM extract itself is not committed. |
| "44,552 residents impacted" | `44 nodes x 1008 people/node`. The per-node population is a constant, not a census join. |
| "24 emergency facilities", "312 vulnerable intersections" | Required a live Overpass query and a DEM that is not in the repository. |
| "answers that in 3 seconds" | No latency benchmark exists. |

### What can be regenerated today

| Claim | Regenerated by | Status |
|---|---|---|
| Resilience Index is monotonic under nested ablation | `tests/test_resilience_index.py` | measured |
| Intervention rankings are invariant across finite RI penalties (1800/3600/7200 s) | `tests/test_resilience_index.py` | measured, on synthetic topologies only |
| RI floor = `baseline_mean / penalty_s`, so RI is **not** comparable across networks | `tests/test_resilience_index.py` | measured |
| Targeted attack does **not** dominate random failure on a homogeneous lattice | `tests/test_no_clamps.py` | measured, synthetic |
| Targeted attack **does** dominate on a chokepoint topology | `tests/test_no_clamps.py` | measured, synthetic |
| Cascade counts are non-monotonic once the forced 65% decay is removed | `tests/test_no_clamps.py` | measured, synthetic |
| A mismatched centrality cache is refused rather than returned | `tests/test_reproducibility.py` | measured |

**No result on a real road network is currently reproducible in this repository,**
because the OSM extract is not committed and the environment used for development
could not reach Overpass. See [`backend/data/README.md`](backend/data/README.md)
for the artifacts required and how to drop them in.

### Data provenance

Every numeric endpoint returns a `data_provenance` block declaring
`measured` / `derived` / `synthetic` / `unavailable`, the artifacts it consumed,
and the modelling assumptions applied. Endpoints whose required input is missing
return **HTTP 503** rather than a substitute value. Currently returning 503 in a
fresh clone: `/simulate/flood`, `/simulate/flood/curve`, `/simulate/equity-metrics`,
`/simulate/traffic-impact`, `/simulate/degradation-forecast`,
`/accessibility/equity`, and `/simulate/evacuate` (unimplemented).

`GET /graph/source` reports the fingerprint of the graph under analysis. Quote it
alongside any number you report.

## Quick Start

### Dependencies are split by what you actually need

| File | Contents | Enables |
|---|---|---|
| `requirements-core.txt` | graph, simulation, API, reports. **No PyTorch.** | everything except `/simulate/flood*` and `/segment/*` |
| `requirements-raster.txt` | core + `rasterio`, `scikit-image` | `/simulate/flood*`, GeoTIFF upload |
| `requirements-ml.txt` | + PyTorch, transformers, etc. (~2.5 GB) | `/segment/*` when `ENABLE_ML=true` |

The segmentation router is **off by default** (`ENABLE_ML=false`). The resilience
engine imports and serves all 19 `/simulate` and 7 `/graph` endpoints with the
entire ML and raster stack absent.

### Backend

```bash
cd backend
python -m venv .venv && source .venv/bin/activate
pip install -r requirements-core.txt

cp .env.example .env          # set GROQ_API_KEY for the copilot

# Fetch the OSM extract. Requires network access to Overpass.
# Without it, /graph/source returns 503 — no graph is synthesised.
python scripts/download_data.py

uvicorn app.main:app --reload --port 8000
curl localhost:8000/graph/source     # record this fingerprint with any result
```

### Frontend

```bash
cd frontend
npm ci
npm run dev                    # http://localhost:3000
```

### Docker

```bash
cp backend/.env.example .env   # set GROQ_API_KEY
docker compose up --build
```

Notes:
* `NEXT_PUBLIC_API_BASE` is **inlined at build time**. Override it as a build
  arg, not a runtime environment variable, and point it at the URL the browser
  reaches (the published host port), not the compose service name.
* `backend/data/` is mounted from the host. Data artifacts are never baked into
  the image; see [`backend/data/README.md`](backend/data/README.md).
* Enable segmentation with
  `BACKEND_REQUIREMENTS=requirements-ml.txt ENABLE_ML=true docker compose up --build`.

### Tests

```bash
cd backend && python -m pytest tests/ -q
STRICT_GRAPH_CACHE=true python -m pytest tests/ -q    # reproducibility mode
```

---

## Feature Coverage

| # | Feature | Module | Status |
|---|---------|--------|--------|
| 1 | Road segmentation (U-Net / SegFormer) | `app/ml/model.py`, `inference.py` | implemented, **no trained checkpoint committed** — runs with random weights |
| 2 | Occlusion augmentation | `app/ml/augmentations.py` | implemented; no occlusion benchmark exists |
| 3 | Pre/post change detection | `app/ml/change_detection.py` | **stub** — computes a diff, discards it, returns fixed constants |
| 4 | Grad-CAM explainability | `app/ml/explain.py` | implemented |
| 5 | Skeleton→graph + MST healing | `app/graph_pipeline/` | implemented. Pixel→lat/lon is a **linear stretch over the AOI bbox**, not a georeferenced transform |
| 6 | Centrality analysis | `app/graph_pipeline/centrality.py` | implemented, fingerprint-keyed cache |
| 7 | Multi-source evacuation | `app/simulation/evacuation.py` | **not implemented** — endpoint returns 503 |
| 8 | Cascading failure | `app/simulation/cascade.py` | implemented; threshold model only, **no load-redistribution physics** |
| 9 | Resilience Index + penalty-free decomposition | `app/simulation/resilience.py` | implemented, tested |
| 10 | Counterfactual intervention validation | `app/api/simulation.py` (`/ablate/prescribe`) | implemented, tested; reports failed interventions |
| 11 | Bhuvan tile integration | `app/integrations/bhuvan.py` | layer config only; **WMS layer names unverified against the live service** |
| 12 | Socio-economic / financial loss | `app/simulation/equity.py`, `traffic_impact.py` | **requires data not in repo** — endpoints return 503. The economic model is a chain of fixed coefficients, not an OD model |
| 13 | Flood / topography | `app/simulation/topography.py` | requires a DEM; **bathtub elevation threshold, no hydrology** |
| 14 | AI copilot | `app/api/copilot.py` | implemented; no evaluation of output grounding |

---

## API Reference

Every numeric response carries a `data_provenance` block. Endpoints marked **503**
return an error naming the missing artifact rather than a substitute value, in a
clone with no data present.

| Endpoint | Method | Description | Fresh clone |
|---|---|---|---|
| `/graph/source` | GET | **Which graph artifact is under analysis** — AOI, version, fingerprint. Cite this with any result. | 503 (no OSM extract) |
| `/graph/metrics` | GET | Connectivity statistics | needs graph |
| `/graph/criticality` | GET | Betweenness, closeness, articulation points, edge betweenness | needs graph |
| `/simulate/ablate` | POST | Node ablation → RI + penalty-free decomposition | needs graph |
| `/simulate/ablate/compare` | POST | Targeted vs. degree vs. random control | needs graph |
| `/simulate/ablate/prescribe` | POST | **Counterfactual intervention validation** | needs graph |
| `/simulate/cascade` | POST | Iterative stress propagation | needs graph |
| `/simulate/route` | POST | Baseline vs. post-ablation routing; severed pairs return `comparison_status` | needs graph |
| `/simulate/fragility` | GET | Percolation curve | needs graph |
| `/simulate/flood`, `/flood/curve` | POST/GET | DEM-threshold inundation | **503** — no DEM |
| `/simulate/equity-metrics` | POST | Vulnerability-weighted criticality | **503** — no `vulnerability.csv` |
| `/simulate/traffic-impact` | POST | Economic impact coefficients | **503** — no `od_matrix.csv` |
| `/simulate/degradation-forecast` | POST | Monte Carlo health projection | **503** — no `road_conditions.csv` |
| `/simulate/evacuate` | POST | Evacuation planning | **503** — not implemented |
| `/accessibility/equity` | GET | Healthcare deserts | **503** — no `worldpop_*.csv` |
| `/copilot/chat` | POST | Grounded LLM chat over live graph context | needs `GROQ_API_KEY` |
| `/reports/generate` | POST | PDF situation report | needs graph |
| `/segment/*` | POST | Road segmentation | only when `ENABLE_ML=true` |

Full list (31 paths): **http://localhost:8000/docs**

---

## Demo Scenario

Requires the OSM extract (see [`backend/data/README.md`](backend/data/README.md)).
Steps depending on absent artifacts are marked.

1. `curl localhost:8000/graph/source` → record the graph fingerprint.
2. **Map → Criticality** → betweenness-ranked junctions.
3. **Simulate → Ablate** → RI, plus `unreachable_fraction` and
   `reachable_path_inflation`. A low RI with inflation ≈ 1.0 means pairs were
   *severed*, not slowed — the scalar alone cannot tell you which.
4. **Simulate → Cascade** → per-iteration stressed counts as measured. Counts may
   rise as well as fall; no decay is imposed.
5. **Simulate → Prescribe** → propose a link, re-run the same attack on the
   hardened graph, read `validation_outcome`. Interventions that fail to help
   report `no_change` or `degrades`.
6. **Flood / Equity / Traffic tabs** → *return 503 without their data artifacts.*
7. **Copilot** → query the graph context.

---

## Known Limitations

Scientific:
* **The flood model is a bathtub elevation threshold.** No flow accumulation, no
  drainage, no rainfall-runoff, no storm-sewer capacity, no depth–disruption
  function. Road failure is binary. Bengaluru's 2022 flooding was largely a
  drainage-failure phenomenon, which this cannot represent.
* **The Resilience Index depends on an arbitrary constant** (`penalty_s`, default
  3600 s) charged per severed origin-destination pair. Its floor is
  `baseline_mean / penalty_s`, so **RI is not comparable across networks.** Use
  the penalty-free `unreachable_fraction` and `reachable_path_inflation` for any
  cross-network statement. Intervention *rankings* are invariant across finite
  penalties (tested) — but so far only on synthetic topologies.
* **Cascade propagation has no load-redistribution physics.** It is a betweenness
  threshold recomputed iteratively.
* **Economic and equity figures are coefficient chains, not models.** Those
  endpoints return 503 without their input data precisely because the numbers
  would otherwise be indistinguishable from measurements.
* **Betweenness on graphs above 5000 nodes uses k=5 pivots** for latency, which
  materially widens approximation error. The API declares this per response.
* **Skeleton→graph coordinates are a linear stretch over the AOI bbox**, not a
  georeferenced affine transform. A graph built from an uploaded tile is
  geospatially wrong, which is why it is kept out of the analysis path.

Engineering:
* No result on a real road network is currently reproducible here — the OSM
  extract is not committed and this development environment could not reach
  Overpass.
* Tests target the scientific claims, not the API surface.
* `GraphStore` is process-global; the backend runs single-worker.

Results are decision-support research output, not operational directives.

---

## Tech Stack

| Layer | Stack |
|-------|-------|
| Frontend | Next.js 14, React 18, TypeScript, Tailwind CSS, Leaflet |
| Backend | FastAPI, Python 3.11 |
| AI/ML | PyTorch, segmentation-models-pytorch, OpenCV |
| Geospatial | OSMnx, NetworkX, GeoPandas, Rasterio, Shapely |
| APIs | Bhuvan WMS, Groq API (LLaMA-3) |

---
## Author

**Shriram Baskaran**

Computer Science Student | AI/ML Enthusiast | Aspiring Machine Learning Engineer

- GitHub: https://github.com/Shriram28Baskar
- LinkedIn: https://www.linkedin.com/in/shriram-baskaran/
- Email: shrirambaskaran21@gmail.com

Passionate about building AI-powered systems, Machine Learning solutions, and real-world applications that create meaningful impact.
