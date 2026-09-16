"""
Traffic Impact Analyzer
Translates network failures into human-readable economic and social metrics.
Uses an Origin-Destination matrix and commuter data to compute:
  - Commuter minutes delayed
  - Person-days of productivity lost
  - Economic loss in INR
"""
import csv
import math
import logging
import os
from typing import Dict, List, Any, Set

import networkx as nx

logger = logging.getLogger(__name__)

DATA_DIR = os.path.join(os.path.dirname(__file__), "..", "..", "data")

# Economic constants for Bengaluru
_AVG_HOURLY_WAGE_INR = 285       # Average across all income groups
_AVG_COMMUTER_TIME_MIN = 54      # BBMP survey baseline (minutes one-way)
_DETOUR_PENALTY_PER_KM = 180     # INR in fuel + depreciation per km detour
_WORKDAYS_PER_YEAR = 250
_BENGALURU_DAILY_COMMUTERS = 9_200_000  # ~9.2M daily vehicular trips


def _load_od_matrix() -> List[Dict]:
    path = os.path.join(DATA_DIR, "census", "od_matrix.csv")
    if not os.path.exists(path):
        return []
    with open(path, newline="") as f:
        return list(csv.DictReader(f))


def _haversine_km(lat1, lon1, lat2, lon2) -> float:
    R = 6371.0
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = math.sin(dlat / 2) ** 2 + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.sin(dlon / 2) ** 2
    return R * 2 * math.asin(math.sqrt(max(0, a)))


def compute_traffic_impact(
    G: nx.Graph,
    ablated_node_ids: List[Any],
) -> Dict[str, Any]:
    """
    Given the original graph and a list of ablated (failed) nodes,
    estimates the human and economic cost of the disruption.
    """
    ablated_set: Set[Any] = set(ablated_node_ids)
    od_rows = _load_od_matrix()

    node_positions = {
        n: (data.get("y", 0.0), data.get("x", 0.0))
        for n, data in G.nodes(data=True)
    }

    # ── 1. Graph-level path-length impact ────────────────────────────────────
    # Sample 30 random source nodes from non-ablated set for speed
    import random
    rng = random.Random(99)
    alive_nodes = [n for n in G.nodes() if n not in ablated_set]

    # Perturbed graph: remove ablated nodes
    G_perturbed = G.copy()
    G_perturbed.remove_nodes_from([n for n in ablated_node_ids if G.has_node(n)])

    sample_size = min(30, len(alive_nodes))
    sample = rng.sample(alive_nodes, sample_size) if sample_size > 0 else []

    baseline_lengths, perturbed_lengths = [], []
    unreachable_pairs = 0
    total_pairs = 0

    for src in sample:
        if not G.has_node(src):
            continue
        try:
            b_paths = nx.single_source_dijkstra_path_length(G, src, weight="length", cutoff=20000)
        except Exception:
            b_paths = {}
        try:
            p_paths = nx.single_source_dijkstra_path_length(G_perturbed, src, weight="length", cutoff=20000) if G_perturbed.has_node(src) else {}
        except Exception:
            p_paths = {}

        for tgt, b_dist in b_paths.items():
            if tgt == src or tgt in ablated_set:
                continue
            total_pairs += 1
            if tgt in p_paths:
                perturbed_lengths.append(p_paths[tgt])
                baseline_lengths.append(b_dist)
            else:
                unreachable_pairs += 1
                baseline_lengths.append(b_dist)
                # Penalise unreachable trips as 3× baseline distance
                perturbed_lengths.append(b_dist * 3)

    avg_baseline_m  = sum(baseline_lengths) / len(baseline_lengths) if baseline_lengths else 0
    avg_perturbed_m = sum(perturbed_lengths) / len(perturbed_lengths) if perturbed_lengths else 0
    avg_detour_m    = max(0, avg_perturbed_m - avg_baseline_m)
    detour_km       = avg_detour_m / 1000

    # ── 2. Topological disruption scale (NOT traffic) ────────────────────────
    #
    # M11. The previous version of this block claimed: "Betweenness centrality
    # perfectly represents the fraction of all shortest paths passing through a
    # node. If we sum the centrality of ablated nodes, we get the exact
    # mathematical fraction of city-wide traffic disrupted!" Three things were
    # wrong with that:
    #
    #   (a) it takes the MAX over ablated nodes, not the sum, as the code below
    #       always did;
    #   (b) `compute_betweenness` divides every score by the graph's maximum
    #       (`all_centrality = {k: v / max_score}`), so what it returns is a
    #       RELATIVE score in [0, 1] where the single most central node is 1.0
    #       by construction, on every graph. It is not a fraction of anything;
    #   (c) betweenness counts shortest PATHS between node pairs. It is not a
    #       traffic flow. No origin-destination matrix or traffic count is used
    #       anywhere in this module.
    #
    # A coefficient `*= 0.25` was applied here, commented "scale it back down to
    # ~25% (the true mathematical max for the top node)", i.e. an attempt to undo
    # (b) with a guessed constant. That guess is graph-dependent and was never
    # measured on any graph. It has been REMOVED and deliberately NOT replaced
    # with another coefficient.
    #
    # What is computed now is exactly:
    #
    #     max_relative_betweenness = max over ablated nodes n of
    #                                    BC(n) / max_j BC(j)
    #
    # a dimensionless ratio in [0, 1] against the most central node of THIS
    # graph. 1.0 means "the most central node was ablated". It is a topological
    # severity indicator, NOT a share of trips, traffic, vehicles or people.
    from app.graph_pipeline.centrality import compute_betweenness
    centrality_scores = compute_betweenness(G)

    max_relative_betweenness = 0.0
    for n in ablated_set:
        try:
            n_int = int(n)
        except ValueError:
            n_int = n
        raw_score = float(centrality_scores.get(n, centrality_scores.get(n_int, 0.0)))
        max_relative_betweenness = max(max_relative_betweenness, raw_score)

    # No cap is applied: compute_betweenness max-normalises, so the value is
    # already in [0, 1] by construction and the previous min(1.0, ...) could
    # never bind.

    # DERIVED, NOT MEASURED: a city-wide commuter constant multiplied by a
    # relative topological score. This is not a trip count and must not be read
    # as one. The field it feeds is named accordingly.
    derived_trip_scale = int(_BENGALURU_DAILY_COMMUTERS * max_relative_betweenness)

    # ── 3. Economic calculations ──────────────────────────────────────────────
    # Extra commute time per person
    # 1. Detour driving time (assuming 30 km/h average speed)
    speed_kmh = 30.0
    detour_minutes = (detour_km / speed_kmh) * 60 if detour_km > 0 else 0
    
    # 2. Gridlock / Congestion Penalty
    # A failed central node causes severe local gridlock regardless of the detour path.
    # We add 10 to 45 minutes of base delay scaling with the criticality of the failure.
    # DERIVED: an invented coefficient (300) applied to a relative topological
    # score. Not calibrated against any congestion measurement. Declared, not removed,
    # because removing it would require inventing a replacement.
    gridlock_minutes = max_relative_betweenness * 300
    
    extra_minutes_per_commuter = detour_minutes + gridlock_minutes

    total_commuter_minutes_lost = derived_trip_scale * extra_minutes_per_commuter
    total_commuter_hours_lost   = total_commuter_minutes_lost / 60

    # Person-days lost = total hours / 8h workday
    person_days_lost = total_commuter_hours_lost / 8

    # Wage loss
    wage_loss_inr = total_commuter_hours_lost * _AVG_HOURLY_WAGE_INR

    # Fuel + vehicle costs for detour
    fuel_loss_inr = derived_trip_scale * detour_km * _DETOUR_PENALTY_PER_KM

    # Logistics / goods transport premium (≈15% of total commuter base)
    logistics_loss_inr = (wage_loss_inr + fuel_loss_inr) * 0.15

    total_economic_loss_inr = wage_loss_inr + fuel_loss_inr + logistics_loss_inr

    # Annualise if disruption lasts a week (7 workdays)
    annual_loss_projection_inr = total_economic_loss_inr * _WORKDAYS_PER_YEAR

    unreachable_pct = (unreachable_pairs / max(1, total_pairs)) * 100

    return {
        "ablated_count":               len(ablated_set),
        # M11: renamed from "affected_daily_trips". The old name implied a measured
        # count of disrupted journeys. It is a city-wide commuter constant scaled by
        # a relative betweenness ratio, with no OD matrix and no traffic counts.
        "derived_trip_scale":          derived_trip_scale,
        "max_relative_betweenness":    round(max_relative_betweenness, 6),
        "avg_baseline_trip_m":         round(avg_baseline_m, 1),
        "avg_perturbed_trip_m":        round(avg_perturbed_m, 1),
        "avg_detour_km":               round(detour_km, 2),
        "extra_minutes_per_commuter":  round(extra_minutes_per_commuter, 1),
        "total_commuter_minutes_lost": round(total_commuter_minutes_lost),
        "total_commuter_hours_lost":   round(total_commuter_hours_lost, 1),
        "person_days_lost":            round(person_days_lost, 1),
        "unreachable_trip_pairs_pct":  round(unreachable_pct, 1),
        "wage_loss_inr":               round(wage_loss_inr),
        "fuel_loss_inr":               round(fuel_loss_inr),
        "logistics_loss_inr":          round(logistics_loss_inr),
        "total_economic_loss_inr":     round(total_economic_loss_inr),
        "annual_loss_projection_inr":  round(annual_loss_projection_inr),
        "derived_trip_scale_definition": (
            "_BENGALURU_DAILY_COMMUTERS (9,200,000, a constant) multiplied by "
            "max_relative_betweenness. NOT a measured or estimated count of "
            "disrupted journeys. No origin-destination matrix, traffic count or "
            "survey is used anywhere in this module."
        ),
        "max_relative_betweenness_definition": (
            "max over ablated nodes of BC(n) / max_j BC(j) on this graph. A "
            "dimensionless ratio in [0,1] against the most central node; 1.0 means "
            "the most central node was ablated. NOT a fraction of traffic."
        ),
        "model_assumptions": [
            "betweenness counts shortest paths between node pairs, not vehicle flow",
            "compute_betweenness max-normalises, so scores are relative to this graph",
            "unreachable trips are penalised at 3x baseline distance (invented)",
            "gridlock delay = max_relative_betweenness x 300 minutes (invented coefficient)",
            "logistics premium = 15% of wage+fuel loss (invented coefficient)",
            "wage 285 INR/h, detour 180 INR/km, 250 workdays/yr, 9.2M commuters: "
            "all unsourced constants",
        ],
    }
