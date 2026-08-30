"""
/copilot/chat — AI Urban Planning Copilot powered by Groq.

POST /copilot/chat  → accepts user question + current graph/simulation context JSON,
                       returns a grounded natural-language response.
"""
import json
import logging
from typing import Optional, Dict, Any

from fastapi import APIRouter, HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from app.integrations.groq_client import groq_chat
from app.graph_pipeline.graph_build import GraphStore
from app.graph_pipeline.metrics import compute_graph_metrics
from app.graph_pipeline.centrality import compute_betweenness

logger = logging.getLogger(__name__)
router = APIRouter()

from app.api.prompt import SYSTEM_PROMPT


class ChatMessage(BaseModel):
    role: str   # "user" or "assistant"
    content: str


class CopilotRequest(BaseModel):
    message: str
    history: Optional[list[ChatMessage]] = []


@router.post("/chat")
async def copilot_chat(req: CopilotRequest):
    """
    Accept a user question and return a grounded answer from the LLM.
    Context is assembled EXCLUSIVELY server-side from the current GraphStore state.
    """
    # Build graph context (purely server-side)
    context = _build_context()

    # Build conversation messages
    messages = [
        {"role": m.role, "content": m.content}
        for m in (req.history or [])
    ]
    # Inject live context as a system-level user message
    context_msg = f"""[LIVE GRAPH CONTEXT]\n{json.dumps(context, indent=2)}\n\n[USER QUESTION]\n{req.message}"""
    messages.append({"role": "user", "content": context_msg})

    try:
        reply = await groq_chat(system=SYSTEM_PROMPT, messages=messages)
    except Exception as exc:
        logger.exception("Groq API error")
        raise HTTPException(status_code=502, detail=f"LLM error: {exc}")

    return JSONResponse({
        "reply": reply,
        "context_snapshot": context,
    })


def _build_context() -> Dict:
    """Assemble a structured context for Copilot exclusively from server state."""
    G_healed = GraphStore.get_healed()
    G_fallback = GraphStore.get_osm_fallback()
    
    G = G_healed or G_fallback
    if G is None:
        return {"status": "no_graph_loaded"}

    from app.graph_pipeline.metrics import compute_graph_metrics
    metrics = compute_graph_metrics(G, fast=True)

    # Base topology summary
    ctx = {
        "graph_loaded": True,
        "graph_state": "BASELINE_FALLBACK" if G_healed is None else "ACTIVE_INCIDENT_SIMULATION",
        "metrics": {
            "num_nodes": metrics.get("num_nodes"),
            "num_edges": metrics.get("num_edges"),
        }
    }

    # If there is an active flood result, append its aggregate metrics
    flood = GraphStore.get_last_flood_result()
    if flood:
        data_type = flood.get("data_type", "FLOOD_SIMULATION")
        ctx["active_scenario"] = data_type
        # Key is "water_level" (no _m suffix) — set by both flood and temporal endpoints
        ctx["water_level_m"] = flood.get("water_level")
        ctx["flooded_nodes_count"] = flood.get("flooded_nodes_count")
        ctx["road_length_flooded_km"] = flood.get("road_length_flooded_km")
        ctx["wards_affected"] = flood.get("wards_affected")
        ctx["hospitals_in_flood_zone"] = flood.get("hospitals_in_flood_zone")
        ctx["rainfall_rate_mm_h"] = flood.get("rainfall_rate_mm_h")
        # Population: stored as int in GraphStore
        pop_val = flood.get("population_in_flood_zone")
        if pop_val is not None:
            ctx["population_estimate"] = pop_val if isinstance(pop_val, int) else pop_val.get("value") if isinstance(pop_val, dict) else pop_val
        if flood.get("scenario"):
            ctx["scenario_name"] = flood.get("scenario")

    # If there is accessibility/resilience impact, append it
    acc = GraphStore.get_last_accessibility_impact()
    if acc:
        ctx["accessibility"] = acc.get("facilities", {})
        ctx["resilience_index"] = acc.get("resilience_index")

    # If historical scenario is loaded, append its facts
    sim = GraphStore.get_last_simulation()
    if sim and sim.get("type") == "historical":
        ctx["active_scenario"] = "Historical Disaster: " + sim.get("scenario_id", "")
        ctx["historical_facts"] = sim.get("observed_historical_facts")
        ctx["limitations"] = sim.get("model_limitations")

    return ctx

class BriefRequest(BaseModel):
    flood_data: Dict[str, Any]
    impact_data: Dict[str, Any]
    ward_data: Dict[str, Any]

BRIEF_SYSTEM_PROMPT = """You are an AI assistant generating an 'Incident Commander Narrative' for a disaster response brief.
You will be provided with VERIFIED STRUCTURED DATA from a topographical flood simulation and its cascading impacts on road networks and emergency facilities.

YOUR TASK:
Write a 1-2 paragraph executive summary narrative of the situation. 

CRITICAL RULES:
1. ONLY use the numbers and facts provided in the JSON data.
2. NEVER invent, hallucinate, or calculate new numbers (e.g. do not guess financial losses, deaths, or percentages).
3. Do not include recommendations or formatting like Markdown headers—just plain text narrative.
4. Keep it concise, urgent but professional, suitable for an Incident Commander.
5. If the data is empty or missing, explicitly state "Insufficient data to generate operational narrative."
"""

@router.post("/brief-narrative")
async def generate_brief_narrative(req: BriefRequest):
    """
    Generate a short AI narrative from structured brief data.
    """
    context_msg = f"""[STRUCTURED VERIFIED DATA]
Flood Data: {json.dumps(req.flood_data)}
Impact Data: {json.dumps(req.impact_data)}
Ward Data: {json.dumps(req.ward_data)}
"""
    try:
        reply = await groq_chat(system=BRIEF_SYSTEM_PROMPT, messages=[{"role": "user", "content": context_msg}])
    except Exception as exc:
        logger.error(f"Groq narrative failed: {exc}")
        # Graceful degradation: return a fallback deterministic string
        reply = "AI narrative generation unavailable. Please refer to the structured data below."

    return JSONResponse({"narrative": reply})

