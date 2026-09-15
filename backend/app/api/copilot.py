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


# ── AMDIROS Autonomous Incident Commander Narrative ───────────────────────────
# Called by main.py run_observation_cycle() — NOT by a user request.
# The LLM narrates a deterministic ActionPlan. It has zero write access
# to any operational decision or state field.

IC_NARRATIVE_SYSTEM = """You are the Incident Commander AI for the Route Resilience AMDIROS platform.

You receive a structured JSON snapshot of the current disaster state and produce a concise, executive Incident Commander briefing formatted as clean bullet points (under 140 words).

Required format:
• Situation: [Rainfall rate (OBSERVED), derived flood threshold (DERIVED), flooded nodes (SIMULATED)]
• Network Impact: [Resilience Index (SIMULATED), affected wards, population at risk]
• Healthcare Access: [Hospital reachability — explicitly name isolated facilities or state all clear]
• Directives: [Evacuation orders (EVACUATE_NOW / EVACUATE_ADVISED), relief camps active]

Rules:
- Output the bullet points directly. Do NOT include <think> or internal reasoning tags.
- Output clean, distinct bullet points separated by newlines. Do NOT output a single wall-of-text paragraph.
- Report ONLY what the data says. Never invent hospitals, ward names, routes, or population numbers.
- Label model outputs accurately: SIMULATED, EXTRAPOLATED, OBSERVED, DERIVED.
- If a category is clear/empty, state it concisely (e.g., 'All 346 facilities reachable; zero isolated.').
- Do NOT hallucinate.
"""


async def generate_incident_narrative(state) -> str:
    """
    Generate an LLM-narrated Incident Commander summary from a DisasterState.

    This function is called by the autonomous loop ONLY for first activation
    or HIGH-severity DecisionEvents. It is never called for MEDIUM/LOW/no-change.
    The LLM receives the state as read-only context and returns a narrative string.
    It has zero write access to ActionPlan or any simulation variable.

    Falls back to build_template_narrative() on any failure.
    """
    from app.simulation.disaster_state import build_template_narrative

    try:
        plan = state.action_plan
        isolated_hospitals = [h.name for h in state.hospital_status if not h.reachable]
        reachable_hospitals = [h.name for h in state.hospital_status if h.reachable]
        evac_now = []
        evac_advised = []
        if plan:
            evac_now = [a.ward_name for a in plan.evacuation_advisories if a.action == "EVACUATE_NOW"]
            evac_advised = [a.ward_name for a in plan.evacuation_advisories if a.action == "EVACUATE_ADVISED"]

        disagree_reports = [
            r for r in state.citizen_reports
            if r.flooding_indicator and r.twin_agreement == "DISAGREES"
        ]

        context = {
            "loop_sequence": state.sequence_no,
            "observed_at_utc": state.observed_at,
            "rainfall_rate_mm_h_OBSERVED": state.rainfall_rate_mm_h,
            "derived_flood_threshold_m": state.water_level_m,
            "flooded_node_count_SIMULATED": state.flooded_node_count,
            "resilience_index_SIMULATED": state.resilience_index,
            "affected_wards": state.affected_wards,
            "population_at_risk_DERIVED": state.population_at_risk,
            "hospitals_isolated": isolated_hospitals,
            "hospitals_reachable_count": len(reachable_hospitals),
            "evacuation_now_wards": evac_now,
            "evacuation_advised_wards": evac_advised,
            "relief_camps": len(plan.relief_camp_positions) if plan else 0,
            "predicted_imminent_nodes_EXTRAPOLATED": len([
                n for n in state.predicted_flood_exposure if n.risk_label == "imminent"
            ]),
            "citizen_reports_with_flooding": len([r for r in state.citizen_reports if r.flooding_indicator]),
            "citizen_twin_disagreements": len(disagree_reports),
            "loop_duration_s": state.loop_duration_s,
            "decision_severity": state.decision_event.severity if state.decision_event else None,
            "decision_trigger": state.decision_event.trigger_reason if state.decision_event else None,
        }

        context_msg = f"[AMDIROS DISASTER STATE SNAPSHOT]\n{json.dumps(context, indent=2)}"
        narrative = await groq_chat(
            system=IC_NARRATIVE_SYSTEM,
            messages=[{"role": "user", "content": context_msg}],
            max_tokens=600,
        )
        if not narrative or not narrative.strip() or narrative.startswith("Copilot is temporarily unavailable") or narrative.startswith("Copilot encountered an error"):
            raise RuntimeError("LLM output is empty or unavailable")
        return narrative.strip()

    except Exception as exc:
        logger.warning(f"generate_incident_narrative failed: {exc} — falling back to template.")
        raise
