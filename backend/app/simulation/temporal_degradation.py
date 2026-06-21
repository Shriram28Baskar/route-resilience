"""
Temporal Degradation Forecaster
Runs Monte Carlo simulations to project network health decay over 10 years
based on road age, maintenance budgets, and traffic load from road_conditions.csv.
"""
import csv
import logging
import math
import os
import random
from typing import Dict, List, Any

import networkx as nx

logger = logging.getLogger(__name__)
DATA_DIR = os.path.join(os.path.dirname(__file__), "..", "..", "data")

_BUDGET_SCENARIOS = {
    "optimistic":  1.30,   # 30% budget increase YoY
    "baseline":    1.00,   # static budget
    "austerity":   0.70,   # 30% budget cut
}


def _load_road_conditions() -> List[Dict]:
    path = os.path.join(DATA_DIR, "infrastructure", "road_conditions.csv")
    if not os.path.exists(path):
        return []
    with open(path, newline="") as f:
        return list(csv.DictReader(f))


def _simulate_segment(row: Dict, years: int, budget_multiplier: float, rng: random.Random) -> List[float]:
    """Simulate health trajectory for a single road segment over `years`."""
    try:
        health = float(row["structural_health_index"])
        degrad = float(row["degradation_rate_per_year"])
        budget = float(row["annual_maintenance_budget_inr"]) * budget_multiplier
    except (KeyError, ValueError):
        return [0.5] * years

    trajectory = []
    for _ in range(years):
        # Maintenance effectiveness based on budget (log scale)
        maint_effect = min(0.06, math.log1p(budget / 2_000_000) * 0.008)
        # Stochastic shock (flood, heavy traffic surge, earthquake)
        shock = rng.gauss(0, 0.015)
        health = max(0.0, min(1.0, health - degrad * rng.uniform(0.8, 1.2) + maint_effect + shock))
        trajectory.append(round(health, 4))
    return trajectory


def run_degradation_forecast(
    G: nx.Graph,
    years: int = 10,
    monte_carlo_runs: int = 50,
    budget_scenario: str = "baseline",
) -> Dict[str, Any]:
    """
    Projects network health and expected node failure rates over `years` years.
    
    Returns:
        forecast_years: list of year labels
        network_health_trajectory: mean network health per year (0-1)
        confidence_band_low / high: 10th/90th percentile across MC runs
        annual_failure_probability: fraction of segments expected to hit critical threshold
        budget_scenario: which scenario was run
        zone_forecasts: per-zone degradation summary
        total_reinvestment_needed_inr: estimated budget needed to keep health >0.4
    """
    roads = _load_road_conditions()
    budget_mult = _BUDGET_SCENARIOS.get(budget_scenario, 1.0)

    if not roads:
        # Fallback: synthetic trajectory based on graph metrics
        base_health = 0.72
        trajectory_mean = [round(base_health - i * 0.03, 3) for i in range(years)]
        return {
            "forecast_years":             list(range(1, years + 1)),
            "network_health_trajectory":  trajectory_mean,
            "confidence_band_low":        [max(0, h - 0.08) for h in trajectory_mean],
            "confidence_band_high":       [min(1, h + 0.08) for h in trajectory_mean],
            "annual_failure_probability": [round(i * 0.04, 3) for i in range(years)],
            "budget_scenario":            budget_scenario,
            "zone_forecasts":             [],
            "total_reinvestment_needed_inr": 0,
            "note":                       "Using synthetic trajectory — road_conditions.csv not found.",
        }

    # ── Monte Carlo over all road segments ────────────────────────────────────
    all_runs: List[List[float]] = []  # shape: [mc_runs × years]
    for run_idx in range(monte_carlo_runs):
        rng = random.Random(run_idx * 7 + 13)
        year_means = []
        for yr in range(years):
            year_health = []
            for row in roads:
                traj = _simulate_segment(row, years, budget_mult, rng)
                year_health.append(traj[yr])
            year_means.append(sum(year_health) / len(year_health))
        all_runs.append(year_means)

    # ── Aggregate statistics ──────────────────────────────────────────────────
    mean_traj, low_traj, high_traj = [], [], []
    for yr in range(years):
        vals = sorted(run[yr] for run in all_runs)
        mean_traj.append(round(sum(vals) / len(vals), 4))
        low_traj.append(round(vals[int(len(vals) * 0.1)], 4))
        high_traj.append(round(vals[int(len(vals) * 0.9)], 4))

    # ── Annual failure probability (fraction of segments health < 0.3) ────────
    fail_probs = []
    rng_main = random.Random(42)
    for yr in range(years):
        critical = sum(
            1 for row in roads
            if _simulate_segment(row, years, budget_mult, rng_main)[yr] < 0.3
        )
        fail_probs.append(round(critical / len(roads), 4))

    # ── Per-zone forecast ─────────────────────────────────────────────────────
    zones_seen: Dict[str, List[float]] = {}
    for row in roads:
        zone = row.get("zone", "Unknown")
        try:
            health = float(row["structural_health_index"])
            degrad = float(row["degradation_rate_per_year"])
        except (KeyError, ValueError):
            continue
        if zone not in zones_seen:
            zones_seen[zone] = []
        # Project 10-year final health
        final_health = max(0, health - degrad * years * budget_mult * 0.85)
        zones_seen[zone].append(final_health)

    zone_forecasts = []
    for zone_name, healths in zones_seen.items():
        avg_final = round(sum(healths) / len(healths), 3)
        zone_forecasts.append({
            "zone":          zone_name,
            "avg_health_y0": round(avg_final + years * 0.025, 3),
            "avg_health_y10": avg_final,
            "risk_level":    "CRITICAL" if avg_final < 0.35 else "HIGH" if avg_final < 0.5 else "MODERATE" if avg_final < 0.65 else "LOW",
        })
    zone_forecasts.sort(key=lambda z: z["avg_health_y10"])

    # ── Reinvestment budget estimate ──────────────────────────────────────────
    critical_segments = [
        row for row in roads
        if _simulate_segment(row, years, budget_mult, random.Random(0))[years - 1] < 0.4
    ]
    # Rough rehab cost: ₹8M/km for minor, ₹25M/km for major roads
    total_reinvest = 0
    for row in critical_segments:
        try:
            length = float(row.get("length_km", 1))
            rtype = row.get("road_type", "minor_road")
            cost_per_km = 25_000_000 if "highway" in rtype else 12_000_000 if "major" in rtype else 6_000_000
            total_reinvest += int(length * cost_per_km)
        except (ValueError, KeyError):
            pass

    return {
        "forecast_years":             list(range(1, years + 1)),
        "network_health_trajectory":  mean_traj,
        "confidence_band_low":        low_traj,
        "confidence_band_high":       high_traj,
        "annual_failure_probability": fail_probs,
        "budget_scenario":            budget_scenario,
        "zone_forecasts":             zone_forecasts,
        "total_reinvestment_needed_inr": total_reinvest,
        "critical_segments_count":    len(critical_segments),
        "monte_carlo_runs":           monte_carlo_runs,
    }
