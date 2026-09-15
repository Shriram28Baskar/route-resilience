"""
Data provenance declarations.

Every endpoint that returns numbers must say where those numbers came from.
The four statuses are mutually exclusive and deliberately blunt:

  measured    - computed from a real input artifact that is present on disk
                (e.g. the OSM road graph, a DEM raster, a census CSV).
  derived     - computed from a measured artifact plus documented modelling
                assumptions or constants that are NOT themselves measured
                (e.g. population-per-node, an assumed travel speed).
  synthetic   - produced by a placeholder model with no real input backing it.
                Must never be presented without this label.
  unavailable - a required input is missing. The endpoint returns HTTP 503
                rather than a number.

Rule: an endpoint may not return a numeric payload whose overall status is
`unavailable`, and may not return a `synthetic` payload without the label
reaching the client.
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field, asdict
from typing import Any, Dict, List, Optional

from fastapi import HTTPException

# ── Status constants ──────────────────────────────────────────────────────────
MEASURED = "measured"
DERIVED = "derived"
SYNTHETIC = "synthetic"
UNAVAILABLE = "unavailable"

_RANK = {MEASURED: 0, DERIVED: 1, SYNTHETIC: 2, UNAVAILABLE: 3}

# ── Repository-relative data root ─────────────────────────────────────────────
BACKEND_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.path.join(BACKEND_ROOT, "data")


def data_path(*parts: str) -> str:
    """Absolute path to a file under backend/data, independent of CWD."""
    return os.path.join(DATA_DIR, *parts)


# ── Registry of the real-world artifacts this system consumes ─────────────────
# Each entry: logical name -> (relative path under backend/data, description).
# Nothing here ships with the repository; see data/README.md for how to obtain
# each artifact. Absence is reported, never substituted.
ARTIFACTS: Dict[str, Dict[str, str]] = {
    "osm_graph": {
        "path": "graphs/osm_fallback.gpickle",
        "description": "OSMnx drive network for the configured AOI bounding box.",
        "obtain": "python scripts/download_data.py (requires network access to Overpass)",
    },
    "dem": {
        "path": "rasters/dem.tif",
        "description": "Digital elevation model covering the AOI, metres above sea level.",
        "obtain": "Bhuvan CartoDEM or SRTM tile clipped to the AOI bbox.",
    },
    "vulnerability_csv": {
        "path": "census/vulnerability.csv",
        "description": "Per-zone socioeconomic vulnerability scores.",
        "obtain": "Census of India ward-level tables; see data/README.md for the schema.",
    },
    "od_matrix_csv": {
        "path": "census/od_matrix.csv",
        "description": "Origin-destination trip counts between zones.",
        "obtain": "Household travel survey or BBMP/BMTC OD study.",
    },
    "road_conditions_csv": {
        "path": "infrastructure/road_conditions.csv",
        "description": "Per-segment structural health, degradation rate, maintenance budget.",
        "obtain": "BBMP road asset register.",
    },
    "worldpop_csv": {
        "path": "infrastructure/worldpop_bengaluru.csv",
        "description": "Ward-level population and vulnerability percentages.",
        "obtain": "WorldPop / Census of India ward tables.",
    },
    "model_checkpoint": {
        "path": "checkpoints/best_model.pth",
        "description": "Trained road-segmentation weights.",
        "obtain": "Train via app/ml/train.py on SpaceNet Roads.",
    },
}


def artifact_present(name: str) -> bool:
    spec = ARTIFACTS.get(name)
    return bool(spec) and os.path.exists(data_path(spec["path"]))


def missing_artifacts(*names: str) -> List[str]:
    return [n for n in names if not artifact_present(n)]


# ── Provenance record ─────────────────────────────────────────────────────────
@dataclass
class Provenance:
    """Provenance block attached to every numeric API response."""

    status: str
    inputs: List[Dict[str, Any]] = field(default_factory=list)
    assumptions: List[str] = field(default_factory=list)
    notes: List[str] = field(default_factory=list)

    def add_artifact(self, name: str, *, required: bool = True) -> "Provenance":
        """Record dependency on a registered artifact and fold in its status."""
        spec = ARTIFACTS.get(name, {})
        present = artifact_present(name)
        self.inputs.append({
            "name": name,
            "kind": "artifact",
            "path": f"data/{spec.get('path', '?')}",
            "present": present,
            "status": MEASURED if present else UNAVAILABLE,
            "obtain": None if present else spec.get("obtain"),
        })
        if not present and required:
            self._fold(UNAVAILABLE)
        elif present:
            self._fold(MEASURED)
        return self

    def add_input(self, name: str, status: str, detail: str = "") -> "Provenance":
        """Record a non-artifact input (an in-memory graph, a derived product)."""
        self.inputs.append({"name": name, "kind": "computed",
                            "status": status, "detail": detail})
        self._fold(status)
        return self

    def assume(self, text: str) -> "Provenance":
        """Record a modelling assumption. Any assumption implies `derived`."""
        self.assumptions.append(text)
        self._fold(DERIVED)
        return self

    def note(self, text: str) -> "Provenance":
        self.notes.append(text)
        return self

    def _fold(self, status: str) -> None:
        if _RANK.get(status, 0) > _RANK.get(self.status, 0):
            self.status = status

    def require_available(self, endpoint: str) -> None:
        """Raise 503 if a required input is missing. Never substitutes a value."""
        if self.status == UNAVAILABLE:
            missing = [i for i in self.inputs if i.get("status") == UNAVAILABLE]
            raise HTTPException(
                status_code=503,
                detail={
                    "error": "required_input_unavailable",
                    "endpoint": endpoint,
                    "message": (
                        f"{endpoint} requires input data that is not present in this "
                        f"deployment. No substitute value is returned."
                    ),
                    "missing": missing,
                    "see": "backend/data/README.md",
                },
            )

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


def measured(*artifacts: str) -> Provenance:
    """Start a provenance record that depends on the listed artifacts."""
    p = Provenance(status=MEASURED)
    for a in artifacts:
        p.add_artifact(a)
    return p


def graph_input(G, label: str = "analysis_graph") -> Dict[str, Any]:
    """Describe the graph a computation ran on, including its fingerprint."""
    from app.graph_pipeline.fingerprint import graph_fingerprint, describe_graph_source
    return {
        "name": label,
        "kind": "graph",
        "status": MEASURED if G is not None else UNAVAILABLE,
        "fingerprint": graph_fingerprint(G) if G is not None else None,
        "source": describe_graph_source(G) if G is not None else None,
        "nodes": G.number_of_nodes() if G is not None else 0,
        "edges": G.number_of_edges() if G is not None else 0,
    }


def with_provenance(payload: Dict[str, Any], prov: Provenance) -> Dict[str, Any]:
    """Attach the provenance block to a response payload."""
    out = dict(payload)
    out["data_provenance"] = prov.to_dict()
    return out
