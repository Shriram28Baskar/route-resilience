"""
Equity & Healthcare Desert Analysis
Calculates zones with poor accessibility and models vulnerable populations.
"""
import logging
import os
from typing import List, Dict, Any

import networkx as nx
from app.simulation.routing import compute_route
from app.graph_pipeline.graph_build import GraphStore

logger = logging.getLogger(__name__)

def generate_equity_analysis(G: nx.Graph, facilities: List[Dict]) -> Dict[str, Any]:
    """
    Generate an equity analysis including deserts, vulnerable populations, and overall score.
    """
    if not facilities:
        return {"equity_score": 0, "deserts": [], "vulnerable_clusters": []}

    # Define bounding box
    xs = [d['x'] for _, d in G.nodes(data=True) if 'x' in d]
    ys = [d['y'] for _, d in G.nodes(data=True) if 'y' in d]
    
    if not xs or not ys:
        return {"equity_score": 0, "deserts": [], "vulnerable_clusters": []}
        
    min_x, max_x = min(xs), max(xs)
    min_y, max_y = min(ys), max(ys)
    
    # 1. Grid out the AOI to find deserts
    grid_size = 5 # 5x5 grid
    x_step = (max_x - min_x) / grid_size
    y_step = (max_y - min_y) / grid_size
    
    deserts = []
    
    # Simple direct distance for demo purposes (routing to every grid cell can be slow)
    # 15 mins at 30km/h = 7.5km. Let's say desert threshold is > 5km from any facility
    DESERT_THRESHOLD_M = 5000 
    
    for i in range(grid_size):
        for j in range(grid_size):
            cx = min_x + (i + 0.5) * x_step
            cy = min_y + (j + 0.5) * y_step
            
            # Find closest facility
            min_dist = float('inf')
            for f in facilities:
                # rough distance in meters
                dist = ((cx - f['lon'])**2 + (cy - f['lat'])**2)**0.5 * 111000
                if dist < min_dist:
                    min_dist = dist
                    
            if min_dist > DESERT_THRESHOLD_M:
                # This zone is a desert
                deserts.append({
                    "lat": cy,
                    "lon": cx,
                    "radius": 1500, # visual radius
                    "nearest_facility_distance_m": min_dist
                })
                
    # 2. Vulnerable Population Clusters — loaded from ward-level population fixture
    clusters = []
    csv_path = os.path.join(
        os.path.dirname(__file__),          # .../app/simulation/
        "..", "..", "data", "infrastructure", "worldpop_bengaluru.csv"
    )
    csv_path = os.path.normpath(csv_path)

    try:
        import csv
        with open(csv_path, newline="", encoding="utf-8") as fh:
            reader = csv.DictReader(fh)
            for row in reader:
                try:
                    cx = float(row["lon"])
                    cy = float(row["lat"])
                    pop = int(row["population_2011"])
                    base_risk = row.get("risk_level", "MEDIUM").strip().upper()

                    # Elevate risk if the ward falls inside a detected desert zone
                    in_desert = any(
                        ((cx - d["lon"]) ** 2 + (cy - d["lat"]) ** 2) ** 0.5 * 111000
                        < d["radius"]
                        for d in deserts
                    )
                    if in_desert and base_risk not in ("CRITICAL", "HIGH"):
                        base_risk = "HIGH"

                    # Build vulnerability type string from CSV percentages
                    elderly_pct = float(row.get("vulnerable_elderly_pct", 0))
                    disabled_pct = float(row.get("vulnerable_disabled_pct", 0))
                    bpl_pct = float(row.get("below_poverty_line_pct", 0))
                    vuln_type = max(
                        [("elderly", elderly_pct), ("disabled", disabled_pct), ("low_income", bpl_pct)],
                        key=lambda x: x[1],
                    )[0]

                    clusters.append({
                        "ward_id": row.get("ward_id", ""),
                        "name": row.get("ward_name", ""),
                        "lat": cy,
                        "lon": cx,
                        "population": pop,
                        "risk_level": base_risk,
                        "type": vuln_type,
                        "elderly_pct": elderly_pct,
                        "disabled_pct": disabled_pct,
                        "bpl_pct": bpl_pct,
                        "nearest_hospital_dist_km": float(
                            row.get("nearest_hospital_dist_km", 0)
                        ),
                        "in_desert": in_desert,
                    })
                except (ValueError, KeyError) as row_err:
                    logger.warning(f"Skipping malformed population row: {row_err}")
    except FileNotFoundError:
        logger.warning(
            f"Population fixture not found at {csv_path}. "
            "Vulnerable cluster analysis will be empty."
        )
        
    # 3. Overall Equity Score
    # Base 100, minus penalty for deserts and high risk clusters
    penalty = len(deserts) * 5 + sum(10 for c in clusters if c["risk_level"] == "HIGH")
    score = max(0, min(100, 100 - penalty))
    
    return {
        "equity_score": score,
        "deserts": deserts,
        "vulnerable_clusters": clusters,
        "total_facilities": len(facilities),
        "desert_count": len(deserts)
    }
