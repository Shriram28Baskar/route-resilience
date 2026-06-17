# Route Resilience

**Occlusion-Robust Road Extraction & Graph-Theoretic Criticality Analysis for Urban Mobility**

Built for ISRO NNRMS — Problem Statement PS4 | 30-hour hackathon

---

## Architecture

```
route-resilience/
├── backend/          Python FastAPI — ML inference, graph pipeline, simulation engine
├── frontend/         Next.js 14 — interactive dashboard, Leaflet map, Copilot chat
├── notebooks/        Jupyter — data exploration, model evaluation, graph analysis
└── docker-compose.yml
```

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
| 3 | Multi-resolution Fusion | `backend/app/ml/inference.py` → `fuse_predictions()` |
| 4 | Explainability Maps (Grad-CAM) | `backend/app/ml/explain.py` |
| 5 | Graph Generation | `backend/app/graph_pipeline/graph_build.py` |
| 6 | MST Healing | `backend/app/graph_pipeline/mst_healing.py` |
| 7 | Centrality Analysis | `backend/app/graph_pipeline/centrality.py` |
| 8 | Connectivity Metrics | `backend/app/graph_pipeline/metrics.py` |
| 9 | Node Ablation | `backend/app/simulation/ablation.py` |
| 10 | Cascading Failure | `backend/app/simulation/cascade.py` |
| 11 | Resilience Index | `backend/app/simulation/resilience.py` |
| 12 | Emergency Route Planning | `backend/app/simulation/routing.py` |
| 13 | Criticality Heatmap | `frontend/app/map/` + `components/RoadMap.tsx` |
| 14 | Hospital Accessibility | `backend/app/api/accessibility.py` + `integrations/overpass.py` |
| 15 | AI Urban Planning Copilot | `backend/app/api/copilot.py` + `frontend/app/copilot/` |

---

## API Reference

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/health` | GET | Health check |
| `/segment/` | POST | Segment uploaded tile → mask + confidence |
| `/segment/explain` | POST | Grad-CAM explainability overlay |
| `/graph/build` | POST | Skeletonize mask → NetworkX graph |
| `/graph/heal` | POST | MST topological healing |
| `/graph/metrics` | GET | Connectivity statistics |
| `/graph/centrality` | GET | Betweenness centrality, ranked |
| `/simulate/ablate` | POST | Node ablation + Resilience Index |
| `/simulate/cascade` | POST | Cascading failure simulation |
| `/simulate/route` | POST | Shortest path, baseline vs. post-ablation |
| `/accessibility/hospitals` | GET | Nearest-hospital distances per node |
| `/copilot/chat` | POST | LLM chat with live graph context |

Interactive docs: **http://localhost:8000/docs**

---

## Model Training

```bash
cd backend

# Download SpaceNet Roads dataset to data/spacenet_roads/{images,masks}/
# Then:

python -m app.ml.train \
  --data-dir data/spacenet_roads \
  --epochs 50 \
  --batch-size 8 \
  --variant unet \
  --encoder resnet50

# Checkpoint saved to data/checkpoints/best_model.pth
```

### Supported variants

| Variant | Encoder | Notes |
|---------|---------|-------|
| `unet` | `resnet50` | Default, fast, solid baseline |
| `deeplabv3plus` | `resnet50` | Better for dense urban scenes |
| `segformer` | MIT-b0 | Transformer backbone, stretch goal |

---

## Demo Scenario (Bengaluru AOI)

1. **Open http://localhost:3000** → dashboard showing live graph metrics
2. **Map → Criticality layer** → see gatekeeper intersections in red
3. **Simulate → Node Ablation** → ablate top-3 by centrality → observe Resilience Index drop
4. **Simulate → Cascade** → watch second-order stressed nodes propagate
5. **Simulate → Emergency Route** → compare baseline vs. rerouted path
6. **Map → Hospitals** → see accessibility impact post-ablation
7. **Explain** → upload a Bengaluru tile → view mask + Grad-CAM
8. **Copilot** → ask "What happens if Silk Board Junction floods?"

---

## Tech Stack

| Layer | Stack |
|-------|-------|
| Frontend | Next.js 14, React 18, TypeScript, Tailwind CSS, Framer Motion, React Leaflet, Recharts |
| Backend | FastAPI, Uvicorn, Python 3.11 |
| AI/ML | PyTorch, segmentation-models-pytorch, Transformers (SegFormer), Albumentations, OpenCV |
| Geospatial | OSMnx, NetworkX, GeoPandas, Rasterio, GDAL, Shapely, scikit-image |
| APIs | Groq API (LLaMA-3 70B), Overpass API, Nominatim |
| Data | SpaceNet Roads, OSM India Extract, Sentinel-2, DeepGlobe |

---

## Team Execution Plan

See `PRD.md` for the full 30-hour two-team execution timeline.

**Sub-Team A** (ML): `backend/app/ml/`, `notebooks/01_*`, `notebooks/02_*`
**Sub-Team B** (Graph/Frontend): `backend/app/graph_pipeline/`, `backend/app/simulation/`, `frontend/`

**Critical fallback:** OSM graph pre-downloaded via `scripts/download_data.py` means Sub-Team B can build and demo the entire dashboard independently of model training progress.

---

## Risks & Mitigations

| Risk | Mitigation |
|------|-----------|
| Model doesn't converge | OSM fallback graph for all downstream pipeline demos |
| Large graph → slow centrality | k-sampling (`k=200`) in `compute_betweenness()` |
| Overpass/Groq rate limits | Static JSON fallbacks in `overpass.py` and `groq_client.py` |
| Disconnected graph breaks path length | LCC-only computation + `disconnected` flag in API responses |
| MST produces unnatural bridges | Angular alignment penalty in `mst_healing.py` |
