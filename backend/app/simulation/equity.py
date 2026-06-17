"""
Equity & Healthcare Desert Analysis
Calculates zones with poor accessibility and models vulnerable populations.
"""
import logging
import random
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
                
    # 2. Vulnerable Population Clusters (Synthetic)
    # Generate 3-5 clusters randomly located, some overlapping with deserts
    clusters = []
    num_clusters = random.randint(3, 5)
    for _ in range(num_clusters):
        cx = min_x + random.random() * (max_x - min_x)
        cy = min_y + random.random() * (max_y - min_y)
        
        # Check if in desert
        in_desert = any(((cx - d['lon'])**2 + (cy - d['lat'])**2)**0.5 * 111000 < d['radius'] for d in deserts)
        pop = random.randint(500, 5000)
        risk = "HIGH" if in_desert else "MEDIUM" if random.random() > 0.5 else "LOW"
        
        clusters.append({
            "lat": cy,
            "lon": cx,
            "population": pop,
            "risk_level": risk,
            "type": random.choice(["elderly", "disabled", "low_income"])
        })
        
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
