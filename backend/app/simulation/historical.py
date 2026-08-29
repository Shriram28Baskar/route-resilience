"""
Historical disaster scenarios for Route Resilience.

Design contract:
- This module stores OBSERVED HISTORICAL FACTS with citations.
- These are model INPUTS, not predetermined model outputs.
- The simulation runs actual algorithms on these inputs.
- Results are NEVER adjusted to match documented outcomes.
- Every displayed statistic must be traceable to a source.

Separation of concerns:
  OBSERVED = documented from external sources (IMD, BBMP, news archives)
  SIMULATED = computed by Route Resilience algorithms from the observed inputs
  COMPARISON = directional agreement check between model and documents (not validation)
"""
from typing import Dict, Any, List, Optional


# ---------------------------------------------------------------------------
# 2022 Bengaluru Urban Flood
# Peak event: September 5, 2022
# ---------------------------------------------------------------------------

BENGALURU_2022_FLOOD: Dict[str, Any] = {
    "id": "bengaluru_2022_urban_flood",
    "name": "2022 Bengaluru Urban Flood",
    "peak_date": "2022-09-05",
    "data_type": "HISTORICAL_SCENARIO",
    "description": (
        "One of the most severe urban flooding events in recent Bengaluru history. "
        "Multiple residential layouts, arterial roads, and IT campuses were submerged. "
        "BBMP declared a disaster-management emergency. Hundreds of families displaced."
    ),

    # ------------------------------------------------------------------
    # OBSERVED HISTORICAL FACTS
    # These values are sourced from external records — NOT computed here.
    # ------------------------------------------------------------------
    "observed": {
        "_label": (
            "OBSERVED — documented from IMD, BBMP, and news archives. "
            "NOT computed by Route Resilience algorithms."
        ),
        "rainfall_mm": 131.0,
        "rainfall_source": "India Meteorological Department (IMD)",
        "rainfall_source_note": (
            "Peak 24-hour rainfall documented at urban Bengaluru IMD stations "
            "on September 5, 2022. HAL Observatory and surrounding urban IMD grid cells "
            "recorded 80–131mm. 131mm is the peak figure cited in IMD bulletins and "
            "multiple BBMP emergency press releases. Different stations recorded "
            "different amounts; 131mm represents the worst-affected zone."
        ),
        "rainfall_precision": "80–131mm range across IMD urban stations; 131mm used as peak input",

        # Qualitative reference only — not a flood boundary dataset
        "known_affected_areas_qualitative": [
            "Bellandur",
            "Koramangala",
            "Ejipura",
            "Domluru",
            "BTM Layout",
            "Bommanahalli",
            "Marathahalli",
            "Sarjapur Road",
        ],
        "known_affected_areas_source": (
            "BBMP emergency press releases and news archives, September 2022"
        ),
        "known_affected_areas_note": (
            "Qualitative reference list. NOT a validated flood-boundary shapefile or "
            "satellite-derived flood extent. These area names are used only for "
            "directional comparison — they are NOT model validation ground truth."
        ),

        "infrastructure_impact_note": (
            "Multiple major IT campuses (Wipro, RGA Tech Park, and others in Sarjapur/Whitefield "
            "corridor), residential layouts, and arterial roads were reported submerged. "
            "Source: BBMP press releases, KSNDMC situation reports, news archives Sep 2022."
        ),
        "reported_families_displaced_note": (
            "Hundreds of families reported displaced across SE Bengaluru. "
            "Exact count varied across sources; no single verified figure used here."
        ),
    },

    # ------------------------------------------------------------------
    # SCENARIO PARAMETERIZATION
    # How the historical event is translated into a model input.
    # ------------------------------------------------------------------
    "scenario_water_level_m": 905.0,
    "scenario_water_level_basis": "calibrated_to_documented_flood_extent",
    "scenario_water_level_derivation": {
        "step_1_rainfall_runoff": {
            "rainfall_mm": 131.0,
            "runoff_coefficient": 0.70,
            "effective_runoff_mm": round(131.0 * 0.70, 4),
            "water_depth_m": round(131.0 * 0.70 / 1000, 6),
            "water_level_m": round(877.0 + 131.0 * 0.70 / 1000, 3),
            "flooded_nodes_at_this_level": "~2 (verified by test)",
            "model_limitation": (
                "Static uniform-runoff model computes water_level = 877.09m from 131mm rainfall. "
                "At this level, only ~2 nodes flood — physically unrealistic for an extreme urban event. "
                "The model's uniform-sheet-flow assumption breaks down for concentrated urban flooding "
                "where drainage blockage, topographic channeling, and backwater effects dominate."
            ),
        },
        "step_2_calibrated_level": {
            "water_level_m": 905.0,
            "basis": (
                "Documented flood zones (Koramangala, Ejipura, Domluru) have terrain elevation "
                "~890–910m per SRTMGL1 DEM. A water level of 905m encompasses these areas. "
                "905m corresponds approximately to the mean terrain elevation of the AOI (measured: 903m), "
                "representing a scenario where low-to-mid elevation areas are inundated. "
                "This is a calibrated parameterization to approximate the documented flood extent — "
                "NOT a physically derived water level from the rainfall model."
            ),
            "why_not_derived_from_rainfall": (
                "The rainfall-to-water-level formula (DEM_min + rainfall × RC / 1000) is designed "
                "for statistical backtest over many events. It does not model urban drainage failure, "
                "concentrated runoff, or backwater flooding. For the 2022 extreme event, "
                "the formula produces a non-representative result (877.09m → 2 nodes). "
                "A calibrated scenario level is the honest alternative."
            ),
        },
    },

    # ------------------------------------------------------------------
    # AOI COVERAGE NOTE
    # Some documented areas fall outside the current graph boundary.
    # ------------------------------------------------------------------
    "aoi_coverage_note": (
        "Current AOI: lat 12.92–12.99, lon 77.57–77.64. "
        "Bellandur (lon ≈77.67), Marathahalli (lon ≈77.70), and Whitefield (lon ≈77.75) "
        "are OUTSIDE this boundary — they cannot be evaluated by the current model. "
        "Koramangala, Ejipura, and Domluru are within or near the AOI boundary."
    ),

    # ------------------------------------------------------------------
    # MODEL LIMITATIONS (all apply to this scenario)
    # ------------------------------------------------------------------
    "model_limitations": [
        "DEM model is static height-threshold inundation — not hydraulic routing or drainage simulation",
        "Rainfall-to-water-level conversion (RC=0.70) does not model drainage blockage — not used for water level derivation in this scenario",
        "Scenario water level (905m) is calibrated to documented flood extent, not physically derived from rainfall",
        "WorldPop 2020 population is a 100m gridded estimate — not census-verified",
        "Ward impact compared only against qualitative news-reported area names — not official flood maps",
        "AOI covers lon 77.57–77.64; Bellandur, Marathahalli, Whitefield (lon 77.65+) are outside boundary",
        "Road graph is from 2023 OSM — minor topology differences from 2022 state possible",
    ],
}


# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------

_SCENARIOS: Dict[str, Dict[str, Any]] = {
    BENGALURU_2022_FLOOD["id"]: BENGALURU_2022_FLOOD,
}


def get_scenario(scenario_id: str) -> Optional[Dict[str, Any]]:
    """Return scenario config by ID, or None if not found."""
    return _SCENARIOS.get(scenario_id)


def list_scenarios() -> List[Dict[str, Any]]:
    """Return summary list of all available historical scenarios."""
    return [
        {
            "id": s["id"],
            "name": s["name"],
            "peak_date": s["peak_date"],
            "description": s["description"],
            "data_type": s["data_type"],
        }
        for s in _SCENARIOS.values()
    ]
