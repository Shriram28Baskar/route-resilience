"""
Equity-Weighted Resilience Analysis
Fuses network betweenness centrality with socioeconomic vulnerability data
to produce a crisis priority score for every node in the graph.
"""
import csv
import math
import logging
import os
from typing import Dict, List, Any

import networkx as nx

logger = logging.getLogger(__name__)

# Bengaluru bounding box
_BBOX = {"lat_min": 12.85, "lat_max": 13.15, "lon_min": 77.50, "lon_max": 77.80}

DATA_DIR = os.path.join(os.path.dirname(__file__), "..", "..", "data")

# Reference node count for the full city (baseline undamaged graph).
# This is used to calculate how many nodes were LOST in each zone.
_BASELINE_NODE_COUNT: int = 13500


def _load_vulnerability() -> List[Dict]:
    """Load vulnerability CSV; returns empty list if file not found."""
    path = os.path.join(DATA_DIR, "census", "vulnerability.csv")
    if not os.path.exists(path):
        return []
    with open(path, newline="") as f:
        return list(csv.DictReader(f))


def compute_equity_metrics(
    G: nx.Graph,
    centrality: Dict[str, float],
) -> Dict[str, Any]:
    """
    Returns an equity-weighted resilience report for the current graph.

    crisis_priority_nodes: nodes ranked by (centrality × vulnerability),
    identifying segments whose failure would disproportionately hurt
    vulnerable populations.

    The equity score drops when disaster (flood/ablation) destroys nodes
    in vulnerable zones, which is the correct real-world behavior.
    """
    vuln_zones = _load_vulnerability()

    node_positions = {
        n: (data.get("y", 0.0), data.get("x", 0.0))
        for n, data in G.nodes(data=True)
    }

    total_surviving_nodes = len(node_positions)
    # Estimate fraction of city destroyed
    destroyed_fraction = max(
        0.0,
        1.0 - total_surviving_nodes / max(_BASELINE_NODE_COUNT, 1)
    )

    # --- Assign each node its nearest zone's vulnerability score ---------------
    node_vuln: Dict[Any, float] = {}
    for node, (lat, lon) in node_positions.items():
        best_score = 0.25  # default mid-low
        best_dist = float("inf")
        for z in vuln_zones:
            try:
                zlat, zlon = float(z["lat"]), float(z["lon"])
                dist = math.hypot(lat - zlat, lon - zlon)
                if dist < best_dist:
                    best_dist = dist
                    best_score = float(z["vulnerability_score"])
            except (ValueError, KeyError):
                pass
        node_vuln[node] = best_score

    # --- Compute crisis priority = betweenness × vulnerability ------------------
    crisis = {}
    for node, btw in centrality.items():
        v = node_vuln.get(node, 0.25)
        crisis[node] = round(btw * v, 6)

    ranked = sorted(crisis.items(), key=lambda x: x[1], reverse=True)

    # --- Find spatial extent of the current graph -------------------------------
    lats = [lat for lat, lon in node_positions.values()]
    lons = [lon for lat, lon in node_positions.values()]
    if lats and lons:
        min_lat, max_lat = min(lats), max(lats)
        min_lon, max_lon = min(lons), max(lons)
    else:
        min_lat, max_lat, min_lon, max_lon = 0, 0, 0, 0

    # --- Zone-level aggregate summary -------------------------------------------
    zone_impact = []
    for z in vuln_zones:
        try:
            zlat, zlon = float(z["lat"]), float(z["lon"])
            
            # Skip zones that are outside the graph's actual spatial coverage area
            if not (min_lat - 0.02 < zlat < max_lat + 0.02 and min_lon - 0.02 < zlon < max_lon + 0.02):
                continue
                
            pop = int(z.get("population", 0))
            vuln = float(z["vulnerability_score"])

            # Count SURVIVING high-centrality nodes near this zone (within ~2km ≈ 0.018°)
            surviving_critical = sum(
                1 for node, (lat, lon) in node_positions.items()
                if math.hypot(lat - zlat, lon - zlon) < 0.018
                and centrality.get(node, 0) > 0.01
            )

            # A zone is HIGH risk if:
            # 1. It is inherently vulnerable AND the city has been heavily hit, OR
            # 2. It is inherently vulnerable AND has no surviving critical nodes nearby
            #    (meaning those roads were wiped out by the disaster)
            zone_is_hit = destroyed_fraction > 0.1  # more than 10% of city destroyed
            isolated = surviving_critical == 0 and zone_is_hit

            if (vuln > 0.45 and zone_is_hit) or (vuln > 0.35 and isolated):
                risk_level = "HIGH"
            elif vuln > 0.3 or (zone_is_hit and vuln > 0.2):
                risk_level = "MEDIUM"
            else:
                risk_level = "LOW"

            zone_impact.append({
                "zone_name":             z["zone_name"],
                "lat":                   zlat,
                "lon":                   zlon,
                "population":            pop,
                "vulnerability":         round(vuln, 3),
                "critical_nodes_nearby": surviving_critical,
                "risk_level":            risk_level,
            })
        except (ValueError, KeyError):
            continue

    # --- Top crisis nodes --------------------------------------------------------
    top_crisis_nodes = []
    for node_id, score in ranked[:20]:
        lat, lon = node_positions.get(node_id, (0, 0))
        top_crisis_nodes.append({
            "node_id":          str(node_id),
            "lat":              round(lat, 5),
            "lon":              round(lon, 5),
            "centrality":       round(centrality.get(node_id, 0), 5),
            "vulnerability":    round(node_vuln.get(node_id, 0), 3),
            "crisis_priority":  score,
        })

    # --- Overall equity score (0-100) -------------------------------------------
    # Base penalty for overall city destruction
    destruction_penalty = round(destroyed_fraction * 60)  # up to -60 pts for a total wipeout

    if zone_impact:
        high_risk_zones = sum(1 for z in zone_impact if z["risk_level"] == "HIGH")
        medium_risk_zones = sum(1 for z in zone_impact if z["risk_level"] == "MEDIUM")
        zone_penalty = high_risk_zones * 8 + medium_risk_zones * 2
        equity_score = max(0, 100 - destruction_penalty - zone_penalty)
    else:
        equity_score = max(0, 75 - destruction_penalty)

    return {
        "equity_score":          equity_score,
        "crisis_priority_nodes": top_crisis_nodes,
        "zone_impact_matrix":    zone_impact,
        "total_zones_analyzed":  len(zone_impact),
        "high_risk_zones":       sum(1 for z in zone_impact if z["risk_level"] == "HIGH"),
    }

