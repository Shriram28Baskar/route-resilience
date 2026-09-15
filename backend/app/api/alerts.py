"""
/alerts — Steps 9 + 10: Live weather + alert dispatch.

GET  /alerts/weather          → current OWM weather for Bengaluru
GET  /alerts/forecast         → 24h rainfall forecast
POST /alerts/weather-trigger  → auto-check live rain → dispatch alert if threshold exceeded
POST /alerts/dispatch         → manually fire a flood alert (email + browser WS)
WS   /alerts/ws               → WebSocket endpoint for browser push notifications
"""
import logging
from typing import Optional

from fastapi import APIRouter, WebSocket, Query
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from app.integrations.weather import fetch_current_weather, fetch_forecast_rain
from app.integrations.alerts import dispatch_alert, ws_connect, send_email_alert
from app.data.backtest import rainfall_to_water_level
from app.simulation.topography import flood_ablate, initialize_elevations
from app.graph_pipeline.graph_build import GraphStore

logger = logging.getLogger(__name__)
router = APIRouter()

# Rainfall threshold (mm/hr) above which we auto-dispatch an alert
AUTO_ALERT_THRESHOLD_MM = 15.6   # IMD "moderate" threshold


class ManualAlertRequest(BaseModel):
    severity: str = "high"      # critical | high | moderate | low
    title: str
    message: str
    send_email: bool = True
    send_ws: bool = True
    recipient_email: Optional[str] = None   # override default recipients


class WeatherTriggerRequest(BaseModel):
    threshold_mm: float = AUTO_ALERT_THRESHOLD_MM
    send_email: bool = True
    send_ws: bool = True


@router.get("/weather")
async def get_current_weather():
    """
    Step 9: Fetch live weather for Bengaluru from OpenWeatherMap.

    Returns current conditions, 1h/3h rainfall, and flood risk classification.
    Source: OpenWeatherMap Current Weather API (real-time).
    """
    data = await fetch_current_weather()
    return JSONResponse(data)


@router.get("/forecast")
async def get_forecast(hours: int = Query(24, ge=3, le=120)):
    """
    Step 9: Fetch OWM 5-day forecast for Bengaluru filtered to the requested window.

    Returns per-3h rainfall values, risk level, and peak risk classification.
    Source: OpenWeatherMap 5-Day Forecast API (real-time).
    """
    data = await fetch_forecast_rain(hours=hours)
    return JSONResponse(data)


@router.post("/weather-trigger")
async def weather_trigger(req: WeatherTriggerRequest):
    """
    Step 9+10: Check live rainfall and auto-dispatch alert if threshold exceeded.

    Flow:
      1. Fetch current OWM rainfall for Bengaluru
      2. If rainfall_1h >= threshold_mm:
         a. Convert to estimated flood water level (DEM model)
         b. Run flood simulation
         c. Build alert payload
         d. Dispatch email + browser WS alert
      3. Return {triggered: bool, weather: {...}, alert_result: {...}}

    Threshold default: 15.6 mm/hr (IMD "moderate" — historically causes flooding
    in low-lying Bengaluru wards).
    """
    weather = await fetch_current_weather()
    if "error" in weather:
        return JSONResponse({"triggered": False, "error": weather["error"]}, status_code=503)

    rain_1h = weather.get("current_rainfall_1h_mm", 0.0)
    risk = weather.get("risk", {})

    if rain_1h < req.threshold_mm:
        return JSONResponse({
            "triggered": False,
            "reason": f"Rainfall {rain_1h:.2f}mm/hr below threshold {req.threshold_mm}mm/hr",
            "weather": weather,
        })

    # Convert live rain to flood water level
    wl_data = rainfall_to_water_level(rain_1h)
    water_level_m = wl_data["water_level_m"]

    # Run flood simulation
    G = GraphStore.get_healed() or GraphStore.get_osm_fallback()
    flooded_nodes = []
    flooded_count = 0
    if G is not None:
        initialize_elevations(G)
        flooded_nodes = flood_ablate(G, water_level_m)
        flooded_count = len(flooded_nodes)

    # Determine severity from risk level
    severity_map = {
        "none": "low", "low": "low", "moderate": "moderate",
        "high": "high", "very_high": "critical", "extreme": "critical"
    }
    severity = severity_map.get(risk.get("level", "low"), "moderate")

    alert_result = await dispatch_alert(
        severity=severity,
        title=f"Live Rainfall Alert — {rain_1h:.1f}mm/hr in Bengaluru",
        message=(
            f"OpenWeatherMap reports {rain_1h:.1f}mm rainfall in the last hour over Bengaluru. "
            f"DEM flood model derives threshold {water_level_m:.3f}m. "
            f"Predicted impact: {flooded_count} road network nodes affected."
        ),
        details={
            "Rainfall (1h)": f"{rain_1h:.2f} mm",
            "Risk Level": risk.get("level", "").upper(),
            "Derived Flood Threshold": f"{water_level_m:.3f} m",
            "Predicted Flooded Nodes": flooded_count,
            "Flood Model": "SRTMGL1_30m_static_approximation",
            "Weather Source": "OpenWeatherMap_Current_Weather_API",
        },
        send_email=req.send_email,
        send_ws=req.send_ws,
    )

    return JSONResponse({
        "triggered": True,
        "weather": weather,
        "flood_estimate": wl_data,
        "flooded_nodes_count": flooded_count,
        "alert_result": alert_result,
    })


@router.post("/dispatch")
async def dispatch_manual_alert(req: ManualAlertRequest):
    """
    Step 10: Manually fire a flood alert through email and/or browser WebSocket.

    Use for: testing alerts, manually triggered notifications for ongoing events.
    """
    result = await dispatch_alert(
        severity=req.severity,
        title=req.title,
        message=req.message,
        details={"Manual alert": "Triggered via /alerts/dispatch API"},
        send_email=req.send_email,
        send_ws=req.send_ws,
    )
    return JSONResponse(result)


@router.websocket("/ws")
async def alerts_websocket(websocket: WebSocket):
    """
    Step 10: WebSocket endpoint for browser push notifications.

    Connect from frontend:
      const ws = new WebSocket('ws://localhost:8000/alerts/ws');
      ws.onmessage = (e) => { const alert = JSON.parse(e.data); ... };

    Receives JSON flood alert events whenever dispatch_alert() is called.
    """
    await ws_connect(websocket)
