"""
Alert system for Route Resilience — Step 10.

Supports two alert channels:
  1. Email via Gmail SMTP (App Password auth) — sends HTML flood alert email
  2. Browser push via WebSocket — real-time in-app notification

Email config:
  GMAIL_SENDER:   Gmail address that sends the alerts (set via env or hardcoded below)
  GMAIL_APP_PASS: App password (lnjw qdyf ygpw pvzb)
  ALERT_RECIPIENTS: comma-separated list of recipient emails

WebSocket:
  Connected frontends subscribe to ws://localhost:8000/alerts/ws
  When an alert fires, all connected clients receive a JSON message
"""

import asyncio
import json
import logging
import os
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from typing import Dict, Any, List, Set
from fastapi import WebSocket

logger = logging.getLogger(__name__)

# ── Email config ──────────────────────────────────────────────────────────────
GMAIL_SENDER    = os.environ.get("GMAIL_SENDER", "shrirambaskaran21@gmail.com")
GMAIL_APP_PASS  = os.environ.get("GMAIL_APP_PASS", "lnjw qdyf ygpw pvzb")
ALERT_RECIPIENTS = [
    r.strip() for r in
    os.environ.get("ALERT_RECIPIENTS", GMAIL_SENDER).split(",")
    if r.strip()
]

# ── WebSocket connection registry ─────────────────────────────────────────────
_ws_clients: Set[WebSocket] = set()


async def ws_connect(websocket: WebSocket):
    """Register a new WebSocket client."""
    await websocket.accept()
    _ws_clients.add(websocket)
    logger.info(f"Alert WS client connected. Total: {len(_ws_clients)}")
    try:
        while True:
            # Keep alive — wait for client disconnect
            await websocket.receive_text()
    except Exception:
        pass
    finally:
        _ws_clients.discard(websocket)
        logger.info(f"Alert WS client disconnected. Total: {len(_ws_clients)}")


async def broadcast_ws(payload: Dict[str, Any]):
    """Broadcast alert to all connected WebSocket clients."""
    if not _ws_clients:
        return
    message = json.dumps(payload)
    dead = set()
    for ws in list(_ws_clients):
        try:
            await ws.send_text(message)
        except Exception:
            dead.add(ws)
    _ws_clients -= dead


# ── Email builder ──────────────────────────────────────────────────────────────

def _build_email_html(alert: Dict[str, Any]) -> str:
    severity = alert.get("severity", "unknown").upper()
    colour = {
        "CRITICAL": "#c0392b",
        "HIGH":     "#e67e22",
        "MODERATE": "#f1c40f",
        "LOW":      "#27ae60",
    }.get(severity, "#7f8c8d")

    rows = ""
    for k, v in alert.get("details", {}).items():
        rows += f"<tr><td style='padding:4px 8px;font-weight:bold'>{k}</td><td style='padding:4px 8px'>{v}</td></tr>"

    return f"""
<!DOCTYPE html>
<html>
<body style="font-family:sans-serif;margin:0;padding:0;background:#f4f4f4">
<div style="max-width:600px;margin:32px auto;background:#fff;border-radius:8px;overflow:hidden;box-shadow:0 2px 8px rgba(0,0,0,.15)">
  <div style="background:{colour};padding:24px 32px;color:#fff">
    <h1 style="margin:0;font-size:24px">⚠️ Route Resilience Flood Alert</h1>
    <p style="margin:8px 0 0;opacity:.9">{alert.get('title','Flood Event Detected')}</p>
  </div>
  <div style="padding:24px 32px">
    <p><strong>Severity:</strong> <span style="color:{colour}">{severity}</span></p>
    <p>{alert.get('message','')}</p>
    <table style="border-collapse:collapse;width:100%;margin-top:16px;font-size:14px">
      <thead><tr style="background:#f0f0f0"><th style="padding:6px 8px;text-align:left">Field</th><th style="padding:6px 8px;text-align:left">Value</th></tr></thead>
      <tbody>{rows}</tbody>
    </table>
    <hr style="margin:24px 0;border:none;border-top:1px solid #eee">
    <p style="font-size:12px;color:#888">
      Source: Route Resilience — ISRO NNRMS PS4 Disaster Intelligence Platform<br>
      Data: SRTMGL1 DEM · OpenWeatherMap · WorldPop 2020 · BBMP Wards
    </p>
  </div>
</div>
</body>
</html>
"""


def send_email_alert(alert: Dict[str, Any]) -> Dict[str, Any]:
    """
    Send an HTML flood alert email via Gmail SMTP.

    Returns {success: bool, recipients: [...], error: str|None}
    """
    if GMAIL_SENDER == "PLACEHOLDER@gmail.com":
        logger.warning("Email alert not sent — GMAIL_SENDER not configured.")
        return {"success": False, "error": "GMAIL_SENDER not configured", "recipients": []}

    if not ALERT_RECIPIENTS:
        return {"success": False, "error": "No alert recipients configured", "recipients": []}

    subject = f"[Route Resilience] {alert.get('severity','').upper()} Flood Alert — {alert.get('title','')}"
    html_body = _build_email_html(alert)

    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = GMAIL_SENDER
    msg["To"] = ", ".join(ALERT_RECIPIENTS)
    msg.attach(MIMEText(html_body, "html"))

    try:
        with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
            server.login(GMAIL_SENDER, GMAIL_APP_PASS)
            server.sendmail(GMAIL_SENDER, ALERT_RECIPIENTS, msg.as_string())
        logger.info(f"Alert email sent to {ALERT_RECIPIENTS}")
        return {"success": True, "recipients": ALERT_RECIPIENTS, "error": None}
    except Exception as e:
        logger.error(f"Email alert failed: {e}")
        return {"success": False, "recipients": [], "error": str(e)}


# ── Unified alert dispatcher ───────────────────────────────────────────────────

async def dispatch_alert(
    severity: str,
    title: str,
    message: str,
    details: Dict[str, Any],
    send_email: bool = True,
    send_ws: bool = True,
) -> Dict[str, Any]:
    """
    Fire a flood alert through all configured channels.

    severity: 'critical' | 'high' | 'moderate' | 'low'
    """
    alert = {
        "type": "flood_alert",
        "severity": severity,
        "title": title,
        "message": message,
        "details": details,
    }

    results = {}

    if send_ws:
        await broadcast_ws({"event": "flood_alert", "payload": alert})
        results["websocket"] = {"sent": True, "clients": len(_ws_clients)}

    if send_email:
        email_result = send_email_alert(alert)
        results["email"] = email_result

    return {
        "alert": alert,
        "dispatch_results": results,
    }
