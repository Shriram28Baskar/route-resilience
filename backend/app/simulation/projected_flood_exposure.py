"""
projected_flood_exposure.py — Projected Flood Exposure ETA predictor.

For each alive graph node, computes estimated minutes until the node's
elevation would be reached by rising flood water, under the linear
effective-runoff persistence assumption (same as temporal_projection.py).

Data honesty contract:
  All outputs carry:
    data_type         = "EXTRAPOLATED"
    projection_basis  = "linear_effective_runoff_persistence"

  This is NOT a hydrodynamic simulation. It assumes the current OWM
  rainfall rate persists unchanged and uses the static DEM bathtub model.
  Results represent order-of-magnitude exposure windows, not precise forecasts.
"""
import logging
from typing import List

import networkx as nx

from app.data.backtest import URBAN_RUNOFF_COEFFICIENT

logger = logging.getLogger(__name__)

ETA_PROJECTION_BASIS = "linear_effective_runoff_persistence"
HORIZON_MINUTES = 90


def risk_label_for_eta(eta_minutes: float) -> str:
    """Return risk label string for a given ETA in minutes."""
    if eta_minutes < 15:
        return "imminent"
    elif eta_minutes < 30:
        return "critical"
    elif eta_minutes < 60:
        return "warning"
    else:
        return "watch"


def predict_flood_exposure_eta(
    G_alive: nx.Graph,
    water_level_m: float,
    rainfall_rate_mm_h: float,
    runoff_coefficient: float = URBAN_RUNOFF_COEFFICIENT,
    horizon_minutes: int = HORIZON_MINUTES,
) -> List[dict]:
    """
    Compute projected flood exposure ETA for every alive graph node.

    Algorithm (O(N) — pure arithmetic on node elevation attributes):
      rise_rate_m_per_min = (rainfall_rate_mm_h × RC) / (1000 × 60)
      eta_minutes = (node_elevation_m - water_level_m) / rise_rate_m_per_min

    Args:
        G_alive:            Graph with flooded nodes already removed.
        water_level_m:      Current DEM flood water level (m ASL). DERIVED.
        rainfall_rate_mm_h: OWM rain.1h — current rate (mm/h). OBSERVED.
        runoff_coefficient: Urban RC (default 0.70, Bengaluru urban).
        horizon_minutes:    Only report nodes within this window (default 90min).

    Returns:
        List of dicts, sorted by eta_minutes ascending.
        Empty list if no rain or no nodes within horizon.

    Data type: EXTRAPOLATED under linear_effective_runoff_persistence.
    """
    if rainfall_rate_mm_h <= 0:
        logger.debug("No rainfall — no flood exposure ETAs computed.")
        return []

    # Rise rate: how fast water level climbs (m per minute)
    rise_rate_m_per_min = (rainfall_rate_mm_h * runoff_coefficient) / (1000.0 * 60.0)

    if rise_rate_m_per_min <= 0:
        return []

    results = []
    nodes_missing_elevation = 0

    for node_id, data in G_alive.nodes(data=True):
        elev_m = data.get("elevation")
        if elev_m is None:
            nodes_missing_elevation += 1
            continue

        delta_m = elev_m - water_level_m
        if delta_m <= 0:
            # Already at or below water — should have been ablated; skip safely
            continue

        eta_minutes = delta_m / rise_rate_m_per_min

        if eta_minutes > horizon_minutes:
            continue

        label = risk_label_for_eta(eta_minutes)
        lat = data.get("y")
        lon = data.get("x")

        methodology = (
            f"Node elevation {elev_m:.2f}m is {delta_m:.3f}m above derived flood threshold "
            f"({water_level_m:.3f}m). At rainfall {rainfall_rate_mm_h:.1f}mm/h "
            f"× RC={runoff_coefficient:.2f}, rise rate {rise_rate_m_per_min*1000:.4f}mm/min. "
            f"Estimated exposure in ~{eta_minutes:.1f} min [EXTRAPOLATED, linear persistence]. "
            "NOT a hydrodynamic forecast."
        )

        results.append({
            "node_id": str(node_id),
            "lat": lat,
            "lon": lon,
            "elevation_m": round(elev_m, 2),
            "current_water_level_m": round(water_level_m, 3),
            "delta_elevation_m": round(delta_m, 3),
            "eta_minutes": round(eta_minutes, 1),
            "risk_label": label,
            "data_type": "EXTRAPOLATED",
            "projection_basis": ETA_PROJECTION_BASIS,
            "methodology_note": methodology,
        })

    if nodes_missing_elevation > 0:
        logger.debug(
            f"predict_flood_exposure_eta: {nodes_missing_elevation} nodes skipped "
            "(elevation attribute not set — run initialize_elevations() first)."
        )

    results.sort(key=lambda r: r["eta_minutes"])
    logger.info(
        f"Projected flood exposure: {len(results)} nodes within {horizon_minutes}min "
        f"horizon at {rainfall_rate_mm_h:.1f}mm/h, water={water_level_m:.3f}m."
    )
    return results
