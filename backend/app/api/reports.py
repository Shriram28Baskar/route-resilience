"""
/reports - Situation Report Generation API
"""
import logging
from typing import List

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from app.graph_pipeline.graph_build import GraphStore
from app.reports.generator import generate_pdf_report
from app.graph_pipeline.metrics import compute_graph_metrics
from app.graph_pipeline.centrality import compute_betweenness, get_gatekeepers
from app.simulation.population import estimate_population_impact

logger = logging.getLogger(__name__)
router = APIRouter()

class ReportRequest(BaseModel):
    city_name: str = "Bengaluru"
    sections: List[str]
    timeline_seed_nodes: List[str] = []

@router.post("/generate")
def generate_report(req: ReportRequest):
    """
    Generate a comprehensive PDF situation report.
    """
    G = GraphStore.get_healed() or GraphStore.get_osm_fallback()
    if G is None:
        raise HTTPException(status_code=404, detail="No active graph available to generate report.")

    try:
        # Pre-compute required data based on requested sections
        global_resilience = None
        pop_impact = None
        timeline_data = None
        top_gatekeepers = get_gatekeepers(G, top_n=5)
        
        metrics = compute_graph_metrics(G)
        lcc_fraction = metrics.get("largest_component_fraction", 0.0)
        global_resilience = {
            "score": (0.7 * lcc_fraction) + (0.3 * 1.0), # Baseline is 100% connected
            "metrics": metrics
        }
        
        if "Population Impact Analysis" in req.sections:
            # Baseline pop impact is 0
            pop_impact = estimate_population_impact(G, G)
            
        if "Disaster Progression Timeline" in req.sections:
            node_map = {str(n): n for n in G.nodes()}
            seeds = []
            if req.timeline_seed_nodes:
                seeds = [node_map[nid] for nid in req.timeline_seed_nodes if nid in node_map]
            else:
                seeds = [node_map[str(g["node_id"])] for g in top_gatekeepers[:3] if str(g["node_id"]) in node_map]
            
            from app.simulation.timeline import run_progression_timeline
            try:
                timeline_data = run_progression_timeline(G, seeds, repair_rate=2, max_days=10)
            except Exception as e:
                logger.error(f"Failed to compute timeline for report: {e}")
                timeline_data = None

        pdf_stream = generate_pdf_report(
            city_name=req.city_name,
            sections=req.sections,
            global_resilience=global_resilience,
            pop_impact=pop_impact,
            timeline_data=timeline_data,
            top_gatekeepers=top_gatekeepers
        )
        
        return StreamingResponse(
            pdf_stream,
            media_type="application/pdf",
            headers={"Content-Disposition": f"attachment; filename=Situation_Report_{req.city_name.replace(' ', '_')}.pdf"}
        )
        
    except Exception as e:
        logger.error(f"Failed to generate report: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))
