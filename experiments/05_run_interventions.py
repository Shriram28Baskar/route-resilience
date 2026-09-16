#!/usr/bin/env python3
"""
P2.2 step 2 — intervention experiment (H2).

H2  Under an identical disruption, do counterfactually-validated interventions
    produce larger resilience gains than COST-MATCHED naive interventions?

The naive-baseline comparison is the whole test. "Adding an edge to a
partitioned graph improves connectivity" is true by construction and is not a
finding. What is falsifiable is whether Route Resilience's proposal beats
nearest-gap closure at the same budget.

PRIMARY ENDPOINT (pre-registered)
    delta_unreachable_fraction = unreachable_fraction(I0) - unreachable_fraction(I_x)
    Penalty-free. Positive = OD pairs restored.

PROTOCOL
    1. Load the FROZEN scenario file and verify its hash.
    2. For each scenario, ablate the node set on the baseline graph -> I0.
    3. Each method proposes edges under a total added-length budget.
    4. Add the edges to the BASELINE graph, then ablate the IDENTICAL node set.
    5. Both indices are measured against the SAME baseline G.

Route Resilience's proposer (app/api/simulation.py::ablate_prescribe) is called
unmodified. Budgets are charged at the true great-circle length of the proposed
edge, not the 750 m the algorithm assumes internally.

TWO ASYMMETRIES BETWEEN I1 AND I3 THAT THE RESULTS TURN ON
    1. Edge length. I1's proposals are ~2.6x longer (median 1454.8 m vs 556.7 m).
    2. TARGET COMPONENT. `ablate_prescribe` joins comps_sorted[i] to
       comps_sorted[i+1] -- a CHAIN. `propose_nearest_gap` joins comps[0] to
       comps[i+1] -- a STAR centred on the giant component. Measured over a
       120-scenario replay: 24.1% of I1's edges never touch the giant component;
       100% of I3's do. Under a partial budget an I1 edge can merge two minor
       fragments and restore far fewer OD pairs. See POSTMORTEM_H2.md §1.6.

NOTE ON NEW-EDGE SPEED
    Added edges are given 50 kph while every generated edge is 30 kph, so an added
    metre is 1.67x faster than an existing metre. This is irrelevant to the primary
    endpoint (connectivity) but inflates ri_p* and reachable_path_inflation in
    favour of LONG edges -- i.e. in I1's favour. I1 lost anyway.

OUTPUT
    experiments/results/interventions_raw.jsonl   one record per
                                                  (scenario, method, budget)
"""
from __future__ import annotations

import hashlib
import json
import math
import os
import random
import sys
import time
from typing import Dict, List, Optional, Tuple

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))

import networkx as nx

from app.graph_pipeline.graph_build import GraphStore
from app.simulation.ablation import ablate_nodes
from app.simulation.resilience import compute_resilience_index


# The generator module name starts with a digit; load it by path.
import importlib.util as _ilu
_spec = _ilu.spec_from_file_location(
    "scenario_gen", os.path.join(os.path.dirname(__file__), "04_gen_scenarios.py"))
scenario_gen = _ilu.module_from_spec(_spec)
_spec.loader.exec_module(scenario_gen)

haversine_m = scenario_gen.haversine_m
FAMILIES = scenario_gen.FAMILIES

RESULTS = os.path.join(os.path.dirname(__file__), "results")
SCENARIOS_ABS = os.path.join(os.path.dirname(__file__), "scenarios", "scenarios.json")
SCENARIOS_REL = os.path.join(os.path.dirname(__file__), "scenarios", "scenarios_relative.json")

BUDGETS_M = [500.0, 1000.0, 2000.0]
PENALTIES = [1800.0, 3600.0, 7200.0]
ORACLE_POOL = 15            # bounded, deterministic candidate pool (see _oracle_pool)
NEW_EDGE_SPEED_KPH = 50.0


# ── helpers ───────────────────────────────────────────────────────────────────

def edge_length_m(G, u, v) -> float:
    du, dv = G.nodes[u], G.nodes[v]
    return max(haversine_m(du["y"], du["x"], dv["y"], dv["x"]), 1.0)


def add_edge_geometric(G, u, v) -> None:
    L = edge_length_m(G, u, v)
    G.add_edge(u, v, length=L, weight=L, speed_kph=NEW_EDGE_SPEED_KPH,
               time_s=L / (NEW_EDGE_SPEED_KPH * 1000 / 3600), highway="tertiary")


def apply_budget(G, proposals: List[Tuple], budget: float) -> List[Tuple]:
    """Take proposals in rank order while cumulative true length <= budget."""
    taken, spent = [], 0.0
    for u, v in proposals:
        if u == v or G.has_edge(u, v):
            continue
        L = edge_length_m(G, u, v)
        if spent + L <= budget:
            taken.append((u, v))
            spent += L
    return taken


def measure(G_base, G_pert) -> Dict:
    out = {}
    for p in PENALTIES:
        r = compute_resilience_index(G_base, G_pert, penalty_s=p)
        if p == PENALTIES[0]:
            out["unreachable_fraction"] = r["unreachable_fraction"]
            out["reachable_path_inflation"] = r["reachable_path_inflation"]
            out["pairs_evaluated"] = r["pairs_evaluated"]
            out["pairs_severed"] = r["pairs_severed"]
            out["partition_count"] = r["partition_count"]
        out[f"ri_p{int(p)}"] = r["resilience_index"]
    n = G_pert.number_of_nodes()
    out["lcc_fraction"] = (len(max(nx.connected_components(G_pert), key=len)) / n) if n else 0.0
    return out


# ── intervention proposers ────────────────────────────────────────────────────
# Each returns a RANKED list of (u, v) candidate edges on the baseline graph.

def propose_none(G, G_pert, ablated, rng) -> List[Tuple]:
    return []


def propose_route_resilience(G, G_pert, ablated, rng) -> List[Tuple]:
    """I1 — the system under test. Called unmodified."""
    from app.api.simulation import PrescribeRequest, ablate_prescribe
    GraphStore.set_healed(G)
    try:
        body = json.loads(ablate_prescribe(PrescribeRequest(
            ablated_node_ids=[str(n) for n in ablated],
            max_recommendations=3)).body)
    except Exception:
        return []
    nm = {str(n): n for n in G.nodes()}
    out = []
    for s in body.get("suggestions", []):
        u, v = nm.get(s["from_node"]), nm.get(s["to_node"])
        if u is not None and v is not None:
            out.append((u, v))
    return out


def propose_random(G, G_pert, ablated, rng) -> List[Tuple]:
    """I2 — chance floor."""
    alive = sorted(G_pert.nodes())
    if len(alive) < 2:
        return []
    out = []
    for _ in range(200):
        u, v = rng.sample(alive, 2)
        if not G.has_edge(u, v):
            out.append((u, v))
        if len(out) >= 5:
            break
    return out


def propose_nearest_gap(G, G_pert, ablated, rng) -> List[Tuple]:
    """
    I3 — the 'any competent engineer' baseline: shortest geometric edge joining
    the two largest components. When the graph is still connected, join the
    geometrically-closest non-adjacent pair straddling an articulation point.
    """
    comps = sorted(nx.connected_components(G_pert), key=len, reverse=True)
    out = []
    if len(comps) > 1:
        for i in range(min(3, len(comps) - 1)):
            a, b = list(comps[0]), list(comps[i + 1])
            # bound the search deterministically
            a_s = sorted(a, key=lambda n: -G_pert.degree(n))[:40]
            b_s = sorted(b, key=lambda n: -G_pert.degree(n))[:40]
            best, bl = None, float("inf")
            for u in a_s:
                for v in b_s:
                    L = edge_length_m(G, u, v)
                    if L < bl:
                        best, bl = (u, v), L
            if best:
                out.append(best)
        return out

    aps = list(nx.articulation_points(G_pert))
    for ap in aps[:3]:
        nbrs = sorted(G_pert.neighbors(ap), key=lambda n: -G_pert.degree(n))
        best, bl = None, float("inf")
        for i in range(len(nbrs)):
            for j in range(i + 1, len(nbrs)):
                u, v = nbrs[i], nbrs[j]
                if G.has_edge(u, v):
                    continue
                L = edge_length_m(G, u, v)
                if L < bl:
                    best, bl = (u, v), L
        if best:
            out.append(best)
    return out


def propose_highest_degree(G, G_pert, ablated, rng) -> List[Tuple]:
    """I4 — connect the highest-degree non-adjacent pair."""
    ranked = [n for n, _ in sorted(G_pert.degree(), key=lambda x: x[1], reverse=True)[:25]]
    out = []
    for i in range(len(ranked)):
        for j in range(i + 1, len(ranked)):
            u, v = ranked[i], ranked[j]
            if not G.has_edge(u, v):
                out.append((u, v))
        if len(out) >= 5:
            break
    return out[:5]


def _oracle_pool(G, G_pert, rng) -> List[Tuple]:
    """Bounded candidate pool for I5. Deliberately small and deliberately NOT
    exhaustive: at most ORACLE_POOL shortest candidates drawn from the top-12
    highest-degree nodes of the two largest components. See the note at the I5
    call site -- this is not an optimum over all possible edges."""
    comps = sorted(nx.connected_components(G_pert), key=len, reverse=True)
    pool = []
    if len(comps) > 1:
        a = sorted(comps[0], key=lambda n: -G_pert.degree(n))[:12]
        b = sorted(comps[1], key=lambda n: -G_pert.degree(n))[:12]
        pool = [(u, v) for u in a for v in b if not G.has_edge(u, v)]
    else:
        cand = sorted(G_pert.nodes(), key=lambda n: -G_pert.degree(n))[:20]
        pool = [(u, v) for i, u in enumerate(cand) for v in cand[i + 1:] if not G.has_edge(u, v)]
    pool.sort(key=lambda e: edge_length_m(G, *e))     # deterministic order
    return pool[:ORACLE_POOL]


PROPOSERS = {
    "I0_none": propose_none,
    "I1_route_resilience": propose_route_resilience,
    "I2_random": propose_random,
    "I3_nearest_gap": propose_nearest_gap,
    "I4_highest_degree": propose_highest_degree,
    # I5 handled separately: it searches, it does not propose blind.
}


# ── evaluation ────────────────────────────────────────────────────────────────

def evaluate(G, ablated, edges) -> Dict:
    Gh = G.copy()
    for u, v in edges:
        add_edge_geometric(Gh, u, v)
    return measure(G, ablate_nodes(Gh, ablated))


def run_scenario(G, scen: Dict) -> List[Dict]:
    nm = {str(n): n for n in G.nodes()}
    ablated = [nm[s] for s in scen["ablated_nodes"] if s in nm]
    rng = random.Random(scen["seed"])

    G_pert = ablate_nodes(G, ablated)
    base = measure(G, G_pert)

    records = [{
        **{k: scen[k] for k in ("scenario_id", "graph", "family", "k", "replicate", "seed")},
        "method": "I0_none", "budget_m": 0.0, "n_edges_added": 0,
        "length_used_m": 0.0, "proposed_any": False,
        **base,
        "delta_unreachable_fraction": 0.0,
        "delta_ri_p3600": 0.0,
    }]

    for mname, proposer in PROPOSERS.items():
        if mname == "I0_none":
            continue
        proposals = proposer(G, G_pert, ablated, rng)
        for budget in BUDGETS_M:
            taken = apply_budget(G, proposals, budget)
            res = base if not taken else evaluate(G, ablated, taken)
            records.append({
                **{k: scen[k] for k in ("scenario_id", "graph", "family", "k", "replicate", "seed")},
                "method": mname, "budget_m": budget,
                "n_edges_added": len(taken),
                "length_used_m": round(sum(edge_length_m(G, u, v) for u, v in taken), 1),
                "proposed_any": bool(proposals),
                **res,
                "delta_unreachable_fraction": round(
                    (base["unreachable_fraction"] or 0) - (res["unreachable_fraction"] or 0), 8),
                "delta_ri_p3600": round((res["ri_p3600"] or 0) - (base["ri_p3600"] or 0), 6),
            })

    # I5 — "best single edge from a bounded 15-candidate pool".
    #
    # NOT AN ORACLE, NOT AN UPPER BOUND, NOT HEADROOM. It evaluates at most ONE
    # edge, while every other method may buy several within the same budget.
    # Measured consequence on the pre-registered set: I3 beats it in 55 / 78 / 79
    # of 1,212 scenarios at 500 / 1000 / 2000 m, I1 beats it 17 vs 9 at 2000 m
    # (Wilcoxon p = 0.62), and I2 beats it 19 times. Its `_oracle_pool` is also
    # drawn only from the two largest components' highest-degree nodes, so it does
    # not search the space of possible edges. Read it as a bounded single-edge
    # reference point, nothing more. The method key is left as "I5_oracle" so the
    # committed raw records stay joinable; the NAME is wrong, the data is not.
    pool = _oracle_pool(G, G_pert, rng)
    for budget in BUDGETS_M:
        feasible = [e for e in pool if edge_length_m(G, *e) <= budget]
        best, best_res, best_d = None, base, 0.0
        for e in feasible:
            r = evaluate(G, ablated, [e])
            d = (base["unreachable_fraction"] or 0) - (r["unreachable_fraction"] or 0)
            if d > best_d:
                best, best_res, best_d = e, r, d
        records.append({
            **{k: scen[k] for k in ("scenario_id", "graph", "family", "k", "replicate", "seed")},
            "method": "I5_oracle", "budget_m": budget,
            "n_edges_added": 1 if best else 0,
            "length_used_m": round(edge_length_m(G, *best), 1) if best else 0.0,
            "proposed_any": bool(feasible),
            "oracle_pool_size": len(feasible),
            **best_res,
            "delta_unreachable_fraction": round(best_d, 8),
            "delta_ri_p3600": round((best_res["ri_p3600"] or 0) - (base["ri_p3600"] or 0), 6),
        })
    return records


def main():
    os.makedirs(RESULTS, exist_ok=True)
    mode = os.environ.get("SCENARIO_SET", "absolute")
    path_in = SCENARIOS_ABS if mode == "absolute" else SCENARIOS_REL
    with open(path_in) as f:
        blob = json.load(f)

    recorded = blob.pop("sha256_of_body")
    actual = hashlib.sha256(json.dumps(blob, indent=1, sort_keys=True).encode()).hexdigest()
    if actual != recorded:
        sys.exit(f"FROZEN SCENARIO HASH MISMATCH\n  recorded {recorded}\n  actual   {actual}")
    print(f"scenario file verified: sha256 {recorded}")

    graphs = {}
    for fname, fn in FAMILIES.items():
        G = fn()
        graphs[G.graph["label"]] = G

    scenarios = blob["scenarios"]
    only = sys.argv[1] if len(sys.argv) > 1 else None
    if only:
        scenarios = [s for s in scenarios if s["graph"] == only]
    suffix = ("" if mode == "absolute" else "_relative") + (f"_{only}" if only else "")
    out_path = os.path.join(RESULTS, f"interventions_raw{suffix}.jsonl")

    t0 = time.time()
    with open(out_path, "w") as fh:
        for i, scen in enumerate(scenarios, 1):
            for rec in run_scenario(graphs[scen["graph"]], scen):
                fh.write(json.dumps(rec) + "\n")
            if i % 25 == 0 or i == len(scenarios):
                el = time.time() - t0
                print(f"  {i}/{len(scenarios)} scenarios  {el:.0f}s "
                      f"(eta {el/i*(len(scenarios)-i):.0f}s)", flush=True)

    print(f"\nwrote {out_path}")
    print(f"sha256 {hashlib.sha256(open(out_path,'rb').read()).hexdigest()}")


if __name__ == "__main__":
    main()
