"""
Temporal Flood Projection — NOW → +30min → +60min → +90min

Data honesty contract:
  OBSERVED  : Current rainfall rate from OpenWeatherMap /weather API (rain.1h mm).
              This is the measured precipitation in the PAST 1 hour. NOT a forecast.
  EXTRAPOLATED: Future horizons are computed by assuming the CURRENT rainfall rate
               continues unchanged for 30/60/90 minutes. This is a linear
               persistence assumption — NOT a meteorological forecast.
  MODELED   : Inundation, road impact, population, and connectivity are computed
               by the static DEM height-threshold model at each extrapolated level.

OpenWeatherMap free tier (/data/2.5/weather + /forecast):
  - /weather  → current conditions, rain.1h = last 1-hour accumulation
  - /forecast → 3-HOUR interval steps, minimum step = 3 hours
  Sub-hourly (30/60-min) forecasts require OWM OneCall 3.0 (paid) or radar nowcast.
  This module does NOT claim to use a sub-hourly forecast API.

The 3-hour forecast steps are used ONLY to detect the next rainfall event
label and risk level, NOT to derive 30/60/90-min rainfall amounts.
"""

import logging
import math
from typing import Dict, Any, List, Optional

from app.data.backtest import URBAN_RUNOFF_COEFFICIENT, DEM_MIN_M, rainfall_to_water_level

logger = logging.getLogger(__name__)

# Horizons in minutes
HORIZONS_MIN = [0, 30, 60, 90]

# We do not have sub-hourly forecast data — this is the hard limit
DATA_LIMITATION = (
    "OpenWeatherMap free tier provides 3-hour interval forecasts only. "
    "Sub-hourly (30/60/90-min) future rainfall is NOT available from the API. "
    "Future horizons use linear rainfall-persistence extrapolation: "
    "current_rate_mm_h × time_h × RC. This is a MODELLING ASSUMPTION, not a forecast."
)


def build_temporal_projection(
    current_rainfall_1h_mm: float,
    base_water_level_m: float,
    dem_min_m: float = DEM_MIN_M,
    runoff_coefficient: float = URBAN_RUNOFF_COEFFICIENT,
    next_3h_rain_mm: Optional[float] = None,
    observed_source: str = "OpenWeatherMap_Current_Weather_API",
) -> Dict[str, Any]:
    """
    Build a temporal flood projection for NOW, +30min, +60min, +90min.

    Args:
        current_rainfall_1h_mm: OWM rain.1h — past-hour accumulation (mm).
                                 Used as the current rainfall RATE (mm/h).
        base_water_level_m:     Current water level in the AOI (m ASL).
                                 If no active flood, pass the DEM min.
        dem_min_m:              DEM minimum elevation for the AOI.
        runoff_coefficient:     Urban runoff coefficient (default 0.70).
        next_3h_rain_mm:        OWM forecast rain for the next 3h step (mm/3h).
                                Used ONLY as a qualitative label, not for level math.
        observed_source:        Attribution string for observed data.

    Returns:
        dict with four horizon snapshots:
          - horizon_label, minutes_ahead, data_type
          - rainfall_accumulated_mm (cumulative since NOW)
          - water_level_m (projected)
          - methodology_note
    """
    # Current rainfall rate: rain.1h is last-hour accumulation ≈ mm/h
    rainfall_rate_mm_h = max(0.0, current_rainfall_1h_mm)

    horizons = []
    for minutes in HORIZONS_MIN:
        hours_ahead = minutes / 60.0
        # Cumulative rainfall that would accumulate IF current rate persists
        additional_rain_mm = rainfall_rate_mm_h * hours_ahead

        # Effective runoff from additional rain
        additional_runoff_mm = additional_rain_mm * runoff_coefficient
        additional_water_m   = additional_runoff_mm / 1000.0

        # Projected water level = base level + incremental runoff
        projected_wl = round(base_water_level_m + additional_water_m, 3)

        if minutes == 0:
            data_type = "OBSERVED"
            label = "NOW"
            method_note = (
                f"Current water level supplied as base input ({base_water_level_m}m). "
                f"Rainfall rate observed: {rainfall_rate_mm_h}mm/h (OWM rain.1h)."
            )
        else:
            data_type = "EXTRAPOLATED"
            label = f"+{minutes}min"
            method_note = (
                f"Linear persistence extrapolation: base({base_water_level_m}m) + "
                f"{rainfall_rate_mm_h}mm/h × {hours_ahead:.2f}h × RC({runoff_coefficient}) / 1000 "
                f"= +{additional_water_m*1000:.4f}mm depth ≈ {projected_wl}m ASL. "
                f"NOT a meteorological forecast."
            )

        horizons.append({
            "horizon_label":             label,
            "minutes_ahead":             minutes,
            "data_type":                 data_type,
            "rainfall_rate_mm_h":        round(rainfall_rate_mm_h, 2),
            "rainfall_accumulated_mm":   round(additional_rain_mm, 4),
            "effective_runoff_mm":       round(additional_runoff_mm, 4),
            "additional_water_depth_mm": round(additional_water_m * 1000, 4),
            "projected_water_level_m":   projected_wl,
            "methodology_note":          method_note,
        })

    # Qualitative next-event label from 3h forecast step
    next_event_label = None
    if next_3h_rain_mm is not None and next_3h_rain_mm > 0:
        next_event_label = {
            "rain_3h_mm":  round(next_3h_rain_mm, 2),
            "data_type":   "FORECAST_3H_STEP",
            "source":      "OpenWeatherMap_5Day_Forecast_API",
            "note":        (
                "This is the OWM 3-hour forecast step — the earliest available future data point. "
                "It covers the period NOW to NOW+3h and is used ONLY as a qualitative indicator, "
                "not as a 30/60/90-min sub-hourly prediction."
            ),
        }

    return {
        "model":              "linear_rainfall_persistence_extrapolation",
        "data_limitation":    DATA_LIMITATION,
        "observed_source":    observed_source,
        "rainfall_rate_mm_h": round(rainfall_rate_mm_h, 2),
        "rainfall_rate_note": (
            "OWM rain.1h is precipitation observed in the PAST 1 hour. "
            "It is used as the current rainfall RATE (mm/h) for persistence extrapolation."
        ),
        "base_water_level_m": base_water_level_m,
        "runoff_coefficient": runoff_coefficient,
        "dem_min_m":          dem_min_m,
        "horizons":           horizons,
        "next_3h_forecast":   next_event_label,
    }
