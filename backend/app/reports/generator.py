"""
Automated Situation Report Generator.
Generates PDF reports summarizing disaster impact, timeline, and network health.
"""
import io
import logging
from typing import Dict, Any, List

from reportlab.lib.pagesizes import letter
from reportlab.lib import colors
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, Image as RLImage
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import inch

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

logger = logging.getLogger(__name__)

def generate_pdf_report(
    city_name: str,
    sections: List[str],
    global_resilience: Dict[str, Any] = None,
    pop_impact: Dict[str, Any] = None,
    timeline_data: List[Dict[str, Any]] = None,
    top_gatekeepers: List[Dict[str, Any]] = None
) -> io.BytesIO:
    """
    Generates a PDF report stream.
    
    Args:
        city_name: Name of the region.
        sections: List of sections to include ('Global Resilience Score', 'Population Impact Analysis', 'Disaster Progression Timeline').
        global_resilience: Global resilience data.
        pop_impact: Population impact data.
        timeline_data: Data from timeline simulation.
        top_gatekeepers: Gatekeeper nodes data.
        
    Returns:
        BytesIO buffer containing the PDF.
    """
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=letter, rightMargin=72, leftMargin=72, topMargin=72, bottomMargin=18)
    
    styles = getSampleStyleSheet()
    styles.add(ParagraphStyle(name='CenterTitle', parent=styles['Title'], alignment=1))
    styles.add(ParagraphStyle(name='Highlight', parent=styles['Normal'], textColor=colors.darkred, fontName='Helvetica-Bold'))
    
    Story = []
    
    # ── Cover/Header ─────────────────────────────────────────────────────────
    Story.append(Paragraph(f"Situation Report: {city_name}", styles['CenterTitle']))
    Story.append(Spacer(1, 0.2 * inch))
    Story.append(Paragraph("Route Resilience Automated Analytics", styles['Normal']))
    Story.append(Spacer(1, 0.5 * inch))

    # ── Global Resilience Score ──────────────────────────────────────────────
    if "Global Resilience Score" in sections and global_resilience:
        Story.append(Paragraph("1. Global Resilience Score", styles['Heading2']))
        Story.append(Spacer(1, 0.1 * inch))
        
        grs = global_resilience.get("score", 0.0)
        status = "Healthy" if grs > 0.8 else "Degraded" if grs > 0.5 else "Critical"
        
        Story.append(Paragraph(f"Overall City Resilience Score: {grs:.2f} ({status})", styles['Highlight']))
        Story.append(Spacer(1, 0.1 * inch))
        
        data = [
            ["Metric", "Value"],
            ["Total Nodes", str(global_resilience.get("metrics", {}).get("num_nodes", "N/A"))],
            ["LCC Fraction", f"{global_resilience.get('metrics', {}).get('largest_component_fraction', 0)*100:.1f}%"],
            ["Average Degree", str(global_resilience.get("metrics", {}).get("avg_node_degree", "N/A"))]
        ]
        
        t = Table(data, colWidths=[2.5*inch, 2.5*inch])
        t.setStyle(TableStyle([
            ('BACKGROUND', (0,0), (-1,0), colors.HexColor('#00E5B4')),
            ('TEXTCOLOR', (0,0), (-1,0), colors.black),
            ('ALIGN', (0,0), (-1,-1), 'LEFT'),
            ('FONTNAME', (0,0), (-1,0), 'Helvetica-Bold'),
            ('BOTTOMPADDING', (0,0), (-1,0), 12),
            ('BACKGROUND', (0,1), (-1,-1), colors.HexColor('#F3F4F6')),
            ('GRID', (0,0), (-1,-1), 1, colors.white)
        ]))
        Story.append(t)
        Story.append(Spacer(1, 0.3 * inch))

    # ── Population Impact Analysis ───────────────────────────────────────────
    if "Population Impact Analysis" in sections and pop_impact:
        Story.append(Paragraph("2. Population Impact Analysis", styles['Heading2']))
        Story.append(Spacer(1, 0.1 * inch))
        
        affected = pop_impact.get("total_affected", 0)
        percent = pop_impact.get("percent_affected", 0.0)
        
        Story.append(Paragraph(
            f"Estimated Isolated Population: {affected:,} ({percent}%)", 
            styles['Highlight'] if percent > 5 else styles['Normal']
        ))
        Story.append(Spacer(1, 0.1 * inch))
        Story.append(Paragraph(
            "This analysis maps the region's population proportionally across the road network's largest connected component. "
            "Isolated populations are those located on nodes that have been severed from the main city network.",
            styles['Normal']
        ))
        Story.append(Spacer(1, 0.3 * inch))

    # ── Disaster Progression Timeline ────────────────────────────────────────
    if "Disaster Progression Timeline" in sections and timeline_data:
        Story.append(Paragraph("3. Disaster Progression Timeline", styles['Heading2']))
        Story.append(Spacer(1, 0.1 * inch))
        
        # Create chart
        days = [d['day'] for d in timeline_data]
        grs_scores = [d['global_resilience_score'] for d in timeline_data]
        isolated = [d['isolated_population'] / 1000 for d in timeline_data] # in thousands
        
        fig, ax1 = plt.subplots(figsize=(6, 3))
        
        ax1.set_xlabel('Days')
        ax1.set_ylabel('Global Resilience Score', color='tab:blue')
        ax1.plot(days, grs_scores, color='tab:blue', marker='o')
        ax1.tick_params(axis='y', labelcolor='tab:blue')
        ax1.set_ylim(0, 1.1)
        
        ax2 = ax1.twinx()
        ax2.set_ylabel('Isolated Pop (Thousands)', color='tab:red')
        ax2.bar(days, isolated, alpha=0.3, color='tab:red')
        ax2.tick_params(axis='y', labelcolor='tab:red')
        
        fig.tight_layout()
        img_buffer = io.BytesIO()
        plt.savefig(img_buffer, format='png', dpi=150)
        plt.close(fig)
        img_buffer.seek(0)
        
        Story.append(RLImage(img_buffer, width=6*inch, height=3*inch))
        Story.append(Spacer(1, 0.2 * inch))
        
        # Timeline text
        for d in timeline_data:
            Story.append(Paragraph(
                f"<b>Day {d['day']} ({d['phase']}):</b> GRS {d['global_resilience_score']:.2f}, "
                f"Isolated Pop: {d['isolated_population']:,}",
                styles['Normal']
            ))
            Story.append(Spacer(1, 0.05 * inch))
            
        Story.append(Spacer(1, 0.3 * inch))

    # ── Gatekeepers ──────────────────────────────────────────────────────────
    if top_gatekeepers:
        Story.append(Paragraph("Appendix: Top Gatekeeper Nodes", styles['Heading3']))
        Story.append(Spacer(1, 0.1 * inch))
        
        gk_data = [["Rank", "Node ID", "Centrality"]]
        for i, gk in enumerate(top_gatekeepers[:5]):
            gk_data.append([str(i+1), str(gk.get("node_id", "")), f"{gk.get('centrality', 0)*100:.2f}%"])
            
        t_gk = Table(gk_data, colWidths=[1*inch, 2*inch, 2*inch])
        t_gk.setStyle(TableStyle([
            ('BACKGROUND', (0,0), (-1,0), colors.HexColor('#111827')),
            ('TEXTCOLOR', (0,0), (-1,0), colors.white),
            ('ALIGN', (0,0), (-1,-1), 'CENTER'),
            ('FONTNAME', (0,0), (-1,0), 'Helvetica-Bold'),
            ('GRID', (0,0), (-1,-1), 1, colors.lightgrey)
        ]))
        Story.append(t_gk)

    # Build PDF
    doc.build(Story)
    buffer.seek(0)
    return buffer
