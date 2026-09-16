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
    NOT test the real 13,486-node Bengaluru network.

    POST-AUDIT CORRECTION: the reason originally given here -- "that artifact is
    not obtainable in this environment" -- was FALSE. A real Bengaluru Overpass
    extract is committed at
    backend/cache/befdaed17dcd4b1967a71e322ded5946f4da89e1.json and rebuilds
    OFFLINE to a connected 13,486-node / 19,117-edge graph with real geometry.
    This run predates that discovery and did not use it. F7 therefore remains
    UNTESTED AT CITY SCALE -- not because the graph is unavailable, but because
    testing it would be a NEW EXPERIMENT that has not been run.

CRITERION (read this before quoting the headline)
    `ranking_identical_across_finite_penalties` demands that all 20 positions
    agree across all 5 penalties. 8 cases were evaluated, 0 skipped; 0 of 8 were
    identical; top-1 was stable in 3 of 8; the minimum defined Spearman rho
    against the 3600 s reference is 0.390. RI's top pick disagrees with the
    penalty-free metric's top pick in 6 of 8 cases.

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
    # Spearman between each penalty's ranking and the 3600 s reference.
    #
    # RI SATURATION: at a large penalty every candidate can collapse to the same
    # rounded RI (all pairs severed -> RI == baseline_mean/penalty_s, the floor).
    # spearmanr on a constant vector is UNDEFINED and returns NaN. A bare NaN is
    # not valid JSON, so it is emitted as null and the reason is recorded
    # per penalty in `saturated_penalties`. Undefined is NOT zero and is NOT
    # agreement: it means RI discriminated nothing at that penalty.
    from scipy.stats import spearmanr
    import math as _math
    ref = by_penalty["3600"]
    rho = {}
    saturated = []
    for p, sc in by_penalty.items():
        if any(s is None for s in sc) or any(s is None for s in ref):
            rho[p] = None
            continue
        if len(set(sc)) == 1 or len(set(ref)) == 1:
            rho[p] = None
            saturated.append(p)
            continue
        val = float(spearmanr(sc, ref).statistic)
        if _math.isnan(val):
            rho[p] = None
            saturated.append(p)
        else:
            rho[p] = round(val, 6)

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
        "spearman_undefined_penalties": saturated,
        "spearman_null_means": ("undefined, not zero: RI saturated to a single "
                                "constant across all candidates at this penalty"),
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
                        "Bengaluru network was NOT tested here. NOTE (post-audit): a "
                        "real Bengaluru OSM extract IS committed at "
                        "backend/cache/befdaed17dcd4b1967a71e322ded5946f4da89e1.json and "
                        "rebuilds offline to 13,486 nodes / 19,117 edges with real "
                        "geometry. This run predates that discovery and did NOT use it. "
                        "F7 remains UNTESTED at city scale; testing it would be a NEW "
                        "EXPERIMENT and has not been run."),
        "criterion_note": ("ranking_identical_across_finite_penalties requires ALL 20 "
                           "positions to match across ALL 5 penalties. It is a strict "
                           "criterion: a case with 1 discordant pair out of 190 fails it "
                           "exactly as a case with 123 does. Read it alongside "
                           "top1_identical_across_penalties and spearman_vs_3600."),
        "n_cases_note": "8 cases evaluated, 0 skipped.",
        "cases": cases,
    }
    path = os.path.join(RESULTS, "a7_ri_penalty.json")
    with open(path, "w") as f:
        json.dump(payload, f, indent=1)
    print(f"\nwrote {path}\nsha256 {hashlib.sha256(open(path,'rb').read()).hexdigest()}")


if __name__ == "__main__":
    main()
