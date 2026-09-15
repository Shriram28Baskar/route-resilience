#!/usr/bin/env python3
"""
A7 — RI penalty sensitivity at scale.

QUESTION
    The Resilience Index charges an arbitrary constant (penalty_s, default
    3600 s) per severed origin-destination pair. Its floor is
    baseline_mean / penalty_s, so RI is not comparable across networks. The
    question that decides whether RI can back a RECOMMENDATION is narrower:

        does the RANKING of candidate interventions change with the constant?

FAILURE CONDITION (pre-registered, F7)
    If the ranking of interventions differs across finite penalties, RI cannot
    support recommendations and only the penalty-free quantities
    (unreachable_fraction, reachable_path_inflation) may be reported.

SCOPE LIMIT
    P1 tested this on 196- and 400-node fixtures. This run extends it to the
    largest graphs available here (up to ~500 nodes with real geometry). It does
    NOT test the real 13,486-node Bengaluru network: that artifact is not
    obtainable in this environment, and the topology proxy has no coordinates or
    travel times, so RI on it would be meaningless. F7 therefore remains
    UNTESTED AT CITY SCALE and that is reported as a limitation, not resolved.

OUTPUT
    experiments/results/a7_ri_penalty.json
"""
from __future__ import annotations

import hashlib
import importlib.util as ilu
import json
import os
import random
import sys
from typing import Dict, List

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))

import networkx as nx

_spec = ilu.spec_from_file_location(
    "scenario_gen", os.path.join(os.path.dirname(__file__), "04_gen_scenarios.py"))
scenario_gen = ilu.module_from_spec(_spec)
_spec.loader.exec_module(scenario_gen)

from app.simulation.ablation import ablate_nodes
from app.simulation.resilience import compute_resilience_index

RESULTS = os.path.join(os.path.dirname(__file__), "results")
PENALTIES = [900.0, 1800.0, 3600.0, 7200.0, 14400.0]
N_CANDIDATES = 20
SEED = 20260915


def candidate_interventions(G, ablated, rng, n=N_CANDIDATES):
    """Deterministic pool of single-edge interventions to rank."""
    G_pert = ablate_nodes(G, ablated)
    comps = sorted(nx.connected_components(G_pert), key=len, reverse=True)
    pool = []
    if len(comps) > 1:
        a = sorted(comps[0], key=lambda x: -G_pert.degree(x))[:10]
        b = sorted(comps[1], key=lambda x: -G_pert.degree(x))[:10]
        pool = [(u, v) for u in a for v in b if not G.has_edge(u, v)]
    if len(pool) < n:
        cand = sorted(G_pert.nodes(), key=lambda x: -G_pert.degree(x))[:24]
        pool += [(u, v) for i, u in enumerate(cand) for v in cand[i + 1:]
                 if not G.has_edge(u, v)]
    pool.sort(key=lambda e: scenario_gen.haversine_m(
        G.nodes[e[0]]["y"], G.nodes[e[0]]["x"], G.nodes[e[1]]["y"], G.nodes[e[1]]["x"]))
    return pool[:n]


def run(G, ablated, label) -> Dict:
    rng = random.Random(SEED)
    cands = candidate_interventions(G, ablated, rng)
    if len(cands) < 3:
        return {"case": label, "skipped": "fewer than 3 candidate interventions"}

    by_penalty: Dict[str, List[float]] = {}
    for p in PENALTIES:
        scores = []
        for u, v in cands:
            Gh = G.copy()
            L = scenario_gen.haversine_m(G.nodes[u]["y"], G.nodes[u]["x"],
                                         G.nodes[v]["y"], G.nodes[v]["x"])
            Gh.add_edge(u, v, length=L, weight=L, speed_kph=50.0,
                        time_s=L / (50 * 1000 / 3600), highway="tertiary")
            r = compute_resilience_index(G, ablate_nodes(Gh, ablated), penalty_s=p)
            scores.append(r["resilience_index"])
        by_penalty[str(int(p))] = scores

    rankings = {}
    for p, sc in by_penalty.items():
        if any(s is None for s in sc):
            rankings[p] = None
            continue
        rankings[p] = [i for i, _ in sorted(enumerate(sc), key=lambda x: -x[1])]

    valid = [tuple(r) for r in rankings.values() if r is not None]
    # Spearman between each penalty's ranking and the 3600 s reference
    from scipy.stats import spearmanr
    ref = by_penalty["3600"]
    rho = {}
    for p, sc in by_penalty.items():
        if any(s is None for s in sc) or any(s is None for s in ref):
            rho[p] = None
        else:
            rho[p] = round(float(spearmanr(sc, ref).statistic), 6)

    # penalty-free control: does the decomposition rank them identically?
    pf = []
    for u, v in cands:
        Gh = G.copy()
        L = scenario_gen.haversine_m(G.nodes[u]["y"], G.nodes[u]["x"],
                                     G.nodes[v]["y"], G.nodes[v]["x"])
        Gh.add_edge(u, v, length=L, weight=L, speed_kph=50.0,
                    time_s=L / (50 * 1000 / 3600), highway="tertiary")
        r = compute_resilience_index(G, ablate_nodes(Gh, ablated))
        pf.append(-(r["unreachable_fraction"] or 0.0))   # higher = better
    pf_rank = [i for i, _ in sorted(enumerate(pf), key=lambda x: -x[1])]

    return {
        "case": label,
        "n_candidates": len(cands),
        "ri_by_penalty": by_penalty,
        "ranking_by_penalty": rankings,
        "spearman_vs_3600": rho,
        "ranking_identical_across_finite_penalties": len(set(valid)) == 1,
        "top1_identical_across_penalties": len({r[0] for r in valid}) == 1 if valid else None,
        "penalty_free_ranking": pf_rank,
        "penalty_free_top1_matches_ri_top1": (pf_rank[0] == valid[0][0]) if valid else None,
    }


def main():
    os.makedirs(RESULTS, exist_ok=True)
    cases = []
    for fname, fn in scenario_gen.FAMILIES.items():
        G = fn()
        label = G.graph["label"]
        if G.number_of_nodes() < 40:
            continue
        rng = random.Random(SEED)
        # one targeted and one spatial disruption per graph
        bc = nx.betweenness_centrality(G, normalized=True, weight="weight", seed=42)
        targeted = [n for n, _ in sorted(bc.items(), key=lambda x: -x[1])[:10]]
        spatial = scenario_gen.s4_spatial(G, 10, rng)
        for tag, abl in (("targeted_k10", targeted), ("spatial_k10", spatial)):
            res = run(G, abl, f"{label}|{tag}")
            cases.append(res)
            if "skipped" in res:
                print(f"  {res['case']}: SKIPPED ({res['skipped']})")
            else:
                print(f"  {res['case']}: identical_ranking="
                      f"{res['ranking_identical_across_finite_penalties']} "
                      f"top1_identical={res['top1_identical_across_penalties']} "
                      f"rho_vs_3600={res['spearman_vs_3600']}")

    payload = {
        "experiment": "A7_ri_penalty_sensitivity",
        "failure_condition_F7": ("intervention ranking differs across finite "
                                 "penalties => RI cannot support recommendations"),
        "penalties_s": PENALTIES,
        "scope_limit": ("Largest graph tested has ~500 nodes. The real 13,486-node "
                        "Bengaluru network was NOT tested: the artifact is not "
                        "obtainable here and the topology proxy has no geometry or "
                        "travel times. F7 remains untested at city scale."),
        "cases": cases,
    }
    path = os.path.join(RESULTS, "a7_ri_penalty.json")
    with open(path, "w") as f:
        json.dump(payload, f, indent=1)
    print(f"\nwrote {path}\nsha256 {hashlib.sha256(open(path,'rb').read()).hexdigest()}")


if __name__ == "__main__":
    main()
