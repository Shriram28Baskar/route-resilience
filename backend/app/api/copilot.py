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

SYSTEM_PROMPT = """You are an Urban Planning Copilot embedded in the Route Resilience platform — 
a geospatial AI system for analyzing road network criticality and disaster resilience.

You have access to a live summary of the current road graph, including:
- Graph connectivity metrics (components, average path length, density)
- Top gatekeeper nodes (by betweenness centrality)
- Latest simulation results (node ablation, resilience index, cascade steps)
- Hospital accessibility data

When answering questions:
1. Ground every claim in the provided graph/simulation context — do not hallucinate node IDs or scores.
2. Use precise, quantitative language where data supports it (e.g., "Node 42 carries 18% of all shortest paths").
3. Be actionable — suggest specific interventions (alternate routes, redundant links, infrastructure priorities).
4. If asked about a specific location, cross-reference coordinates in the context.
5. Be concise: planners are busy. Lead with the key insight, then elaborate.

If the requested data is not in the context, say so clearly and suggest what analysis should be run next."""


class ChatMessage(BaseModel):
    role: str   # "user" or "assistant"
    content: str


class CopilotRequest(BaseModel):
    message: str
    history: Optional[list[ChatMessage]] = []
    context_override: Optional[Dict[str, Any]] = None   # allow frontend to pass custom context


@router.post("/chat")
async def copilot_chat(req: CopilotRequest):
    """
    Accept a user question and return a grounded answer from the LLM.
    Context is assembled server-side from the current GraphStore state.
    """
    # Build graph context
    context = _build_context(req.context_override)

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


def _build_context(override: Optional[Dict] = None) -> Dict:
    """Assemble a lightweight context dict from the current graph state."""
    if override:
        return override

    G = GraphStore.get_healed() or GraphStore.get_osm_fallback()
    if G is None:
        return {"status": "no_graph_loaded"}

    metrics = compute_graph_metrics(G)
    centrality = compute_betweenness(G, k=min(100, G.number_of_nodes()))
    top_nodes = sorted(centrality.items(), key=lambda x: x[1], reverse=True)[:10]

    return {
        "graph_loaded": True,
        "metrics": metrics,
        "top_gatekeeper_nodes": [
            {"node_id": str(nid), "centrality": round(score, 4), **G.nodes[nid]}
            for nid, score in top_nodes
        ],
        "simulation": GraphStore.get_last_simulation(),
    }
