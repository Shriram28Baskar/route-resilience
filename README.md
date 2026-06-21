# Route Resilience

![Python 3.11](https://img.shields.io/badge/Python-3.11-blue.svg) ![FastAPI](https://img.shields.io/badge/FastAPI-005571?style=flat&logo=fastapi) ![Next.js](https://img.shields.io/badge/Next.js-black?style=flat&logo=next.js) ![Docker](https://img.shields.io/badge/Docker-2496ED?style=flat&logo=docker) ![ISRO Hackathon 2026](https://img.shields.io/badge/ISRO_Hackathon-2026-orange.svg)

**Occlusion-Robust Road Extraction & Graph-Theoretic Criticality Analysis for Urban Mobility**

Built for ISRO NNRMS — Problem Statement PS4 | 30-hour hackathon

> **"When Bengaluru floods—as it did in September 2022—NDRF teams need to know which junction closures isolate the most hospitals within 10 minutes. Our system answers that in 3 seconds."**

---

## Table of Contents
- [Why Route Resilience Matters](#why-route-resilience-matters)
- [Architecture](#architecture)
- [Novel Contributions](#novel-contributions)
- [Dashboard Screenshots](#dashboard-screenshots)
- [ISRO & NDMA Integration](#isro--ndma-integration)
- [Benchmarks & Validation](#benchmarks--validation)
- [Bengaluru AOI Results](#bengaluru-aoi-results)
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

This transforms satellite imagery into actionable disaster-response intelligence.

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
Evacuation Planner
       ↓
AI Copilot + Dashboard
```

### Directory Structure
```
route-resilience/
├── backend/          Python FastAPI — ML inference, graph pipeline, evacuation planner
├── frontend/         Next.js 14 — interactive dashboard, Leaflet map, Copilot chat
├── notebooks/        Jupyter — data exploration, model evaluation, validation
└── docker-compose.yml
```

## Novel Contributions

1. Occlusion-Robust Road Extraction
2. Graph-Theoretic Criticality Analysis
3. Cascading Failure Simulation
4. Dynamic Flood Impact Modeling
5. Capacity-Constrained Evacuation Planning
6. AI Urban Planning Copilot

---

## Dashboard Screenshots

*(Note to team: Replace these placeholders with actual image paths before final submission)*
* `![Critical Junction Analysis](docs/screenshots/critical_junctions.png)`
* `![Node Ablation & Cascade Failure](docs/screenshots/cascade_failure.png)`
* `![Flood Simulation & Equity Impact](docs/screenshots/flood_equity.png)`
* `![Evacuation Planner](docs/screenshots/evacuation_planner.png)`

---

## ISRO & NDMA Integration

We explicitly align with ISRO's National Natural Resources Management System (NNRMS) mandate and NDMA disaster response protocols:
* **ISRO Bhuvan Integration:** Uses Bhuvan WMS/WFS for mapping, rendering ResourceSat-2A LULC layers over the affected AOI.
* **Satellite-Native:** Pre/Post disaster change detection module designed to take Sentinel-2 or ResourceSat tiles to automatically map flood boundaries.
* **Sendai Framework Priority 4:** Includes a multi-source evacuation planner calculating capacity-respecting routing from vulnerable zones to safe shelters.

## Benchmarks & Validation

Model Performance on SpaceNet Roads AOI:
* **IoU:** 0.73 (Target was to beat DeepGlobe 2018 winner at 0.65)
* **F1-Score:** 0.81
* **Occlusion Robustness:** +12% IoU retention vs baseline at 40% occlusion

Graph Criticality Validation (Chennai Floods 2015 & Kerala Floods 2018):
* **Precision@5:** 4/5 (80%) of our top-5 flagged critical nodes matched actual real-world failures/bottlenecks.
* **Precision@10:** 8/10 (80%)

---

## Bengaluru AOI Results

**Road Network:**
- 13,486 intersections
- 16,000+ road segments

**Hospitals:**
- 24 emergency facilities

**Cascade Failure Example:**
- 44 nodes failed
- 5 network partitions
- 44,552 residents impacted

**Flood Simulation:**
- 312 vulnerable intersections identified

**Evacuation:**
- Dynamic rerouting under disaster conditions successfully maintained hospital access.

## Quick Start

### 1. Clone & configure

```bash
git clone https://github.com/your-team/route-resilience.git
cd route-resilience

cp backend/.env.example backend/.env
# Edit backend/.env and set GROQ_API_KEY=<your key>
```

### 2. Backend setup

```bash
cd backend

# Create virtual environment
python -m venv .venv && source .venv/bin/activate  # Linux/Mac
# .venv\Scripts\activate                            # Windows

pip install -r requirements.txt

# Pre-download OSM data and hospital POIs
python scripts/download_data.py

# Start API server
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

### 3. Frontend setup

```bash
cd frontend

npm install
npm run dev           # http://localhost:3000
```

### 4. Docker (full stack)

```bash
# From repo root
cp backend/.env.example .env
# Set GROQ_API_KEY in .env

docker-compose up --build
# Backend → http://localhost:8000
# Frontend → http://localhost:3000
```

---

## Feature Coverage

| # | Feature | Module |
|---|---------|--------|
| 1 | Transformer Road Segmentation | `backend/app/ml/model.py`, `inference.py` |
| 2 | Occlusion Simulation | `backend/app/ml/augmentations.py` |
| 3 | Pre/Post Change Detection | `backend/app/ml/change_detection.py` |
| 4 | Explainability Maps (Grad-CAM) | `backend/app/ml/explain.py` |
| 5 | Graph Generation & MST Topological Healing | `backend/app/graph_pipeline/graph_build.py` |
| 6 | Centrality Analysis | `backend/app/graph_pipeline/centrality.py` |
| 7 | Multi-Source Evacuation | `backend/app/simulation/evacuation.py` |
| 8 | Cascading Failure Simulation | `backend/app/simulation/cascade.py` |
| 9 | Resilience Index | `backend/app/simulation/resilience.py` |
| 10 | Bhuvan Tile Integration | `backend/app/integrations/bhuvan.py`, `RoadMap.tsx` |
| 11 | Socio-Economic & Financial Loss Modeling | `backend/app/simulation/equity.py` |
| 12 | AI Urban Planning Copilot | `backend/app/api/copilot.py` + `frontend/app/copilot/` |

---

## API Reference

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/segment/` | POST | Segment uploaded tile → mask + confidence |
| `/graph/build` | POST | Skeletonize mask → NetworkX graph |
| `/simulate/ablate` | POST | Node ablation + Resilience Index |
| `/simulate/cascade` | POST | Cascading failure simulation |
| `/simulate/evacuate` | POST | Capacity-constrained evacuation routing |
| `/bhuvan/roads` | GET | Proxy to Bhuvan REST API for road data |
| `/reports/generate` | POST | One-click PDF situation report export |

Interactive docs: **http://localhost:8000/docs**

---

## Demo Scenario (Bengaluru AOI)

1. **Open http://localhost:3000** → dashboard showing live graph metrics
2. **Toggle ISRO Layer** → Show Bhuvan ResourceSat-2A overlay
3. **Map → Criticality layer** → see gatekeeper intersections in red
4. **Simulate → Cascade** → Watch animated second-order stressed nodes propagate dynamically
5. **Simulate → Evacuation** → Map optimal shelter assignments for isolated vulnerable zones
6. **Reports** → Export actionable NDMA-compliant PDF brief
7. **Copilot** → Query the Urban Planning AI to recommend a structural intervention (e.g., pre-building a bridge) to resolve the simulated network partition.

---

## Known Limitations

- Current flood model uses elevation thresholds.
- Cascade model uses load-redistribution assumptions.
- Road extraction accuracy decreases under extreme occlusion.
- Results should be treated as decision-support, not operational directives.

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
## 👨‍💻 Author

**Shriram Baskaran**

Computer Science Student | AI/ML Enthusiast | Aspiring Machine Learning Engineer

- GitHub: https://github.com/Shriram28Baskar
- LinkedIn: https://www.linkedin.com/in/shriram-baskaran/
- Email: shrirambaskaran21@gmail.com

Passionate about building AI-powered systems, Machine Learning solutions, and real-world applications that create meaningful impact.
