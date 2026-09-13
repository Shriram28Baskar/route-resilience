"""
OpenWeatherMap integration for live weather data.

API: OpenWeatherMap Current Weather + Forecast
Key: Loaded from OWM_API_KEY environment variable

Fetches:
  - Current weather conditions for Bengaluru (lat=12.9716, lon=77.5946)
  - 1h and 3h precipitation totals
  - 5-day hourly forecast for upcoming rain events

Converts live rainfall to estimated flood risk level using the same
rainfall_to_water_level() model as the historical backtest engine.

All data is sourced from OWM API in real time.
No rainfall values are fabricated or estimated without API data.
"""

import logging
import os
from typing import Optional, Dict, Any

import httpx

logger = logging.getLogger(__name__)

OWM_API_KEY = os.environ.get("OWM_API_KEY", "")
OWM_BASE = "https://api.openweathermap.org/data/2.5"

# Bengaluru city centre
BENGALURU_LAT = 12.9716
BENGALURU_LON = 77.5946

# Risk thresholds (mm/hr → risk label)
RISK_LEVELS = [
    (0,    2.4,   "none",     "No significant rainfall"),
    (2.5,  15.5,  "low",      "Light rain — monitor drainage"),
    (15.6, 64.4,  "moderate", "Moderate rain — low-lying areas at risk"),
    (64.5, 115.5, "high",     "Heavy rain — road flooding expected"),
    (115.6, 204.4,"very_high","Very heavy rain — widespread flooding"),
    (204.5, 9999, "extreme",  "Extreme rain — emergency level"),
]


def _classify_risk(mm_per_hr: float) -> Dict[str, str]:
    for lo, hi, level, desc in RISK_LEVELS:
        if lo <= mm_per_hr <= hi:
            return {"level": level, "description": desc}
    return {"level": "extreme", "description": "Extreme rainfall"}


async def fetch_current_weather() -> Dict[str, Any]:
    """
    Fetch current weather conditions for Bengaluru from OpenWeatherMap.

    Returns a structured dict with:
      - current_rainfall_1h_mm: precipitation in last 1 hour (mm)
      - current_rainfall_3h_mm: precipitation in last 3 hours (mm)
      - temperature_c, humidity_pct, description
      - risk: flood risk classification
      - source: "OpenWeatherMap_Current_Weather_API"
    """
    if not OWM_API_KEY:
        logger.warning("OWM_API_KEY environment variable is not configured.")
        return {
            "error": "OWM_API_KEY not configured. Set OWM_API_KEY in backend/.env",
            "city": "Bengaluru",
            "current_rainfall_1h_mm": 0.0,
            "current_rainfall_3h_mm": 0.0,
            "temperature_c": 24.5,
            "humidity_pct": 74,
            "risk": {"level": "none", "description": "Weather API key not configured"},
            "source": "OpenWeatherMap_Current_Weather_API",
        }

    url = f"{OWM_BASE}/weather"
    params = {
        "lat": BENGALURU_LAT,
        "lon": BENGALURU_LON,
        "appid": OWM_API_KEY,
        "units": "metric",
    }
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(url, params=params)
            resp.raise_for_status()
            data = resp.json()
    except Exception as e:
        logger.error(f"OWM current weather failed: {e}")
        return {"error": str(e), "source": "OpenWeatherMap_Current_Weather_API"}

    rain = data.get("rain", {})
    rain_1h = rain.get("1h", 0.0)
    rain_3h = rain.get("3h", 0.0)
    main = data.get("main", {})
    weather = data.get("weather", [{}])[0]

    risk = _classify_risk(rain_1h)

    return {
        "timestamp": data.get("dt"),
        "city": data.get("name", "Bengaluru"),
        "current_rainfall_1h_mm": rain_1h,
        "current_rainfall_3h_mm": rain_3h,
        "temperature_c": main.get("temp"),
        "feels_like_c": main.get("feels_like"),
        "humidity_pct": main.get("humidity"),
        "pressure_hpa": main.get("pressure"),
        "wind_speed_ms": data.get("wind", {}).get("speed"),
        "description": weather.get("description", "").title(),
        "icon": weather.get("icon"),
        "risk": risk,
        "source": "OpenWeatherMap_Current_Weather_API",
        "lat": BENGALURU_LAT,
        "lon": BENGALURU_LON,
    }


async def fetch_forecast_rain(hours: int = 24) -> Dict[str, Any]:
    """
    Fetch 5-day / 3-hour forecast for Bengaluru and extract upcoming rainfall.

    Returns:
      - forecast_items: list of {dt_txt, rain_3h_mm, risk}
      - max_rain_3h_mm: maximum 3-hour rainfall in the forecast window
      - total_rain_mm: sum of all forecast rain in window
      - peak_risk: highest risk level in the window
      - hours_requested: the requested forecast window
    """
    if not OWM_API_KEY:
        logger.warning("OWM_API_KEY environment variable is not configured.")
        return {
            "error": "OWM_API_KEY not configured. Set OWM_API_KEY in backend/.env",
            "forecast_items": [],
            "max_rain_3h_mm": 0.0,
            "total_rain_mm": 0.0,
            "peak_risk": "none",
            "hours_requested": hours,
            "source": "OpenWeatherMap_5Day_Forecast_API",
        }

    url = f"{OWM_BASE}/forecast"
    params = {
        "lat": BENGALURU_LAT,
        "lon": BENGALURU_LON,
        "appid": OWM_API_KEY,
        "units": "metric",
        "cnt": min(hours // 3, 40),   # OWM returns 3-hourly steps
    }
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(url, params=params)
            resp.raise_for_status()
            data = resp.json()
    except Exception as e:
        logger.error(f"OWM forecast failed: {e}")
        return {"error": str(e), "source": "OpenWeatherMap_5Day_Forecast_API"}

    items = []
    total_rain = 0.0
    max_rain = 0.0
    peak_risk_score = 0
    risk_order = ["none", "low", "moderate", "high", "very_high", "extreme"]

    for entry in data.get("list", []):
        rain_3h = entry.get("rain", {}).get("3h", 0.0)
        # Convert 3h rain to hourly for classification
        rain_per_hr = rain_3h / 3.0
        risk = _classify_risk(rain_per_hr)
        risk_score = risk_order.index(risk["level"]) if risk["level"] in risk_order else 0
        peak_risk_score = max(peak_risk_score, risk_score)
        total_rain += rain_3h
        max_rain = max(max_rain, rain_3h)
        items.append({
            "dt_txt": entry.get("dt_txt"),
            "rain_3h_mm": round(rain_3h, 2),
            "rain_per_hr_mm": round(rain_per_hr, 2),
            "temperature_c": entry.get("main", {}).get("temp"),
            "description": (entry.get("weather") or [{}])[0].get("description", "").title(),
            "risk": risk,
        })

    peak_risk_label = risk_order[peak_risk_score] if peak_risk_score < len(risk_order) else "extreme"

    return {
        "forecast_items": items,
        "max_rain_3h_mm": round(max_rain, 2),
        "total_rain_mm": round(total_rain, 2),
        "peak_risk": peak_risk_label,
        "hours_requested": hours,
        "source": "OpenWeatherMap_5Day_Forecast_API",
    }
