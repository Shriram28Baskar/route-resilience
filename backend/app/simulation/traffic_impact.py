"""
Traffic Impact Analyzer.

STATUS: this module does NOT implement an origin-destination traffic model.

It converts a set of failed nodes into economic figures using (a) sampled
shortest-path inflation measured on the graph and (b) a chain of fixed
constants. The trip-volume term is derived from ONE node's normalised
betweenness, which is a shortest-path count, not a measured flow.

Consequently every monetary figure this module returns is `derived` at best,
and `synthetic` whenever the OD matrix is absent (which is the only mode the
repository currently ships). The caller is responsible for surfacing that
status; see app/provenance.py.

A real implementation requires data/census/od_matrix.csv. Until that artifact
exists the /simulate/traffic-impact endpoint returns 503 rather than numbers.
"""
import csv
import logging
import os
from typing import Dict, List, Any, Set

import networkx as nx

logger = logging.getLogger(__name__)

DATA_DIR = os.path.join(os.path.dirname(__file__), "..", "..", "data")

# Economic constants for Bengaluru
_AVG_HOURLY_WAGE_INR = 285       # Average across all income groups
_DETOUR_PENALTY_PER_KM = 180     # INR in fuel + depreciation per km detour
_WORKDAYS_PER_YEAR = 250
_BENGALURU_DAILY_COMMUTERS = 9_200_000  # ~9.2M daily vehicular trips


def od_matrix_available() -> bool:
    """True when a real OD matrix is present. No fallback is synthesised."""
    return os.path.exists(os.path.join(DATA_DIR, "census", "od_matrix.csv"))


def compute_traffic_impact(
    G: nx.Graph,
    ablated_node_ids: List[Any],
) -> Dict[str, Any]:
    """
    Given the original graph and a list of ablated (failed) nodes,
    estimates the human and economic cost of the disruption.
    """
    ablated_set: Set[Any] = set(ablated_node_ids)

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

    # ── 2. Trip-volume proxy (NOT a measured flow) ───────────────────────────
    # Betweenness is a count of shortest paths, not traffic volume: it assumes
    # uniform demand between all node pairs, which no city satisfies. Using the
    # MAX over ablated nodes (not a sum) and rescaling by a fixed 0.25 makes the
    # result a monotone function of one node's centrality. This is a placeholder
    # for an OD-matrix lookup and is reported as such in the provenance block.
    from app.graph_pipeline.centrality import compute_betweenness
    centrality_scores = compute_betweenness(G)
    
    fraction_traffic_disrupted = 0.0
    for n in ablated_set:
        try:
            n_int = int(n)
        except ValueError:
            n_int = n
        raw_score = float(centrality_scores.get(n, centrality_scores.get(n_int, 0.0)))
        fraction_traffic_disrupted = max(fraction_traffic_disrupted, raw_score)
        
    # The centrality scores are re-normalized to max 1.0 for UI coloring.
    # We scale it back down to ~25% (the true mathematical max for the top node).
    fraction_traffic_disrupted *= 0.25
        
    # Cap at 1.0 (100% of traffic)
    fraction_traffic_disrupted = min(1.0, fraction_traffic_disrupted)
    
    # Base daily commuters in the city
    affected_trips = int(_BENGALURU_DAILY_COMMUTERS * fraction_traffic_disrupted)

    # ── 3. Economic calculations ──────────────────────────────────────────────
    # Extra commute time per person
    # 1. Detour driving time (assuming 30 km/h average speed)
    speed_kmh = 30.0
    detour_minutes = (detour_km / speed_kmh) * 60 if detour_km > 0 else 0
    
    # 2. Gridlock / Congestion Penalty
    # A failed central node causes severe local gridlock regardless of the detour path.
    # We add 10 to 45 minutes of base delay scaling with the criticality of the failure.
    gridlock_minutes = fraction_traffic_disrupted * 300  # 15% disruption = 45 min delay
    
    extra_minutes_per_commuter = detour_minutes + gridlock_minutes

    total_commuter_minutes_lost = affected_trips * extra_minutes_per_commuter
    total_commuter_hours_lost   = total_commuter_minutes_lost / 60

    # Person-days lost = total hours / 8h workday
    person_days_lost = total_commuter_hours_lost / 8

    # Wage loss
    wage_loss_inr = total_commuter_hours_lost * _AVG_HOURLY_WAGE_INR

    # Fuel + vehicle costs for detour
    fuel_loss_inr = affected_trips * detour_km * _DETOUR_PENALTY_PER_KM

    # Logistics / goods transport premium (≈15% of total commuter base)
    logistics_loss_inr = (wage_loss_inr + fuel_loss_inr) * 0.15

    total_economic_loss_inr = wage_loss_inr + fuel_loss_inr + logistics_loss_inr

    # Projection if a disruption of this magnitude recurred on every workday of
    # a year. This is an extrapolation, not a forecast.
    annual_loss_projection_inr = total_economic_loss_inr * _WORKDAYS_PER_YEAR

    unreachable_pct = (unreachable_pairs / max(1, total_pairs)) * 100

    return {
        "model_assumptions": [
            f"trip volume proxied by max normalised betweenness x 0.25 "
            f"(no OD matrix); base {_BENGALURU_DAILY_COMMUTERS:,} daily trips",
            f"gridlock delay = disruption_fraction x 300 minutes (fixed coefficient)",
            f"wage {_AVG_HOURLY_WAGE_INR} INR/hr; detour cost {_DETOUR_PENALTY_PER_KM} INR/km",
            f"unreachable trips charged 3x baseline distance",
            f"logistics premium = 15% of wage+fuel loss",
            f"annual projection = single-event loss x {_WORKDAYS_PER_YEAR} workdays",
        ],
        "ablated_count":               len(ablated_set),
        "affected_daily_trips":        affected_trips,
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
    }
