#!/usr/bin/env python3
"""
POST-MORTEM DIAGNOSTIC — read-only. Not an experiment.

P2.2 is frozen. This script runs NO new comparison and produces NO new claim.
It replays the two proposers on already-frozen scenarios to recover the edges
they selected, because the raw JSONL records how many edges were added and what
they cost but not which endpoints were chosen.

Both proposers are deterministic given (graph, ablated set, seed), so this is a
reproduction of what already happened, not new data. Nothing here is compared
against a hypothesis and nothing is tuned.

Output: experiments/results/postmortem_i1_vs_i3.json
"""
from __future__ import annotations

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

_spec2 = ilu.spec_from_file_location(
    "runner", os.path.join(os.path.dirname(__file__), "05_run_interventions.py"))
runner = ilu.module_from_spec(_spec2)
_spec2.loader.exec_module(runner)

from app.simulation.ablation import ablate_nodes

RESULTS = os.path.join(os.path.dirname(__file__), "results")
SAMPLE = 120          # partitioned scenarios to replay


def main():
    raw = [json.loads(l) for l in open(os.path.join(RESULTS, "interventions_raw.jsonl"))]
    base = {r["scenario_id"]: r for r in raw if r["method"] == "I0_none"}
    partitioned = [s for s, r in base.items() if (r.get("partition_count") or 1) > 1]

    blob = json.load(open(os.path.join(
        os.path.dirname(__file__), "scenarios", "scenarios.json")))
    scen_by_id = {s["scenario_id"]: s for s in blob["scenarios"]}

    graphs = {}
    for fname, fn in scenario_gen.FAMILIES.items():
        G = fn()
        graphs[G.graph["label"]] = G

    rng_pick = random.Random(4242)
    sample = sorted(partitioned)
    if len(sample) > SAMPLE:
        sample = rng_pick.sample(sample, SAMPLE)

    records: List[Dict] = []
    for sid in sample:
        scen = scen_by_id[sid]
        G = graphs[scen["graph"]]
        nm = {str(n): n for n in G.nodes()}
        ablated = [nm[s] for s in scen["ablated_nodes"] if s in nm]
        G_pert = ablate_nodes(G, ablated)
        rng = random.Random(scen["seed"])

        comps = sorted(nx.connected_components(G_pert), key=len, reverse=True)

        i1 = runner.propose_route_resilience(G, G_pert, ablated, rng)
        rng = random.Random(scen["seed"])
        i3 = runner.propose_nearest_gap(G, G_pert, ablated, rng)

        def describe(edges):
            out = []
            for u, v in edges:
                cu = next((i for i, c in enumerate(comps) if u in c), None)
                cv = next((i for i, c in enumerate(comps) if v in c), None)
                out.append({
                    "u": str(u), "v": str(v),
                    "length_m": round(runner.edge_length_m(G, u, v), 1),
                    "deg_u": G_pert.degree(u) if u in G_pert else None,
                    "deg_v": G_pert.degree(v) if v in G_pert else None,
                    "comp_u": cu, "comp_v": cv,
                    "bridges_components": cu is not None and cv is not None and cu != cv,
                })
            return out

        records.append({
            "scenario_id": sid,
            "graph": scen["graph"], "family": scen["family"], "k": scen["k"],
            "n_components": len(comps),
            "component_sizes": [len(c) for c in comps[:5]],
            "I1_edges": describe(i1),
            "I3_edges": describe(i3),
        })

    # ── summary statistics over the replayed sample ──────────────────────────
    import statistics as st

    def flat(key):
        return [e for r in records for e in r[key]]

    i1e, i3e = flat("I1_edges"), flat("I3_edges")

    def summarise(edges, label):
        if not edges:
            return {"label": label, "n": 0}
        br = [e for e in edges if e["bridges_components"]]
        return {
            "label": label,
            "n_edges": len(edges),
            "median_length_m": round(st.median([e["length_m"] for e in edges]), 1),
            "mean_length_m": round(st.mean([e["length_m"] for e in edges]), 1),
            "max_length_m": round(max(e["length_m"] for e in edges), 1),
            "frac_bridging_two_components": round(len(br) / len(edges), 4),
            "median_endpoint_degree": round(
                st.median([d for e in edges for d in (e["deg_u"], e["deg_v"]) if d is not None]), 2),
            "frac_over_500m": round(sum(1 for e in edges if e["length_m"] > 500) / len(edges), 4),
            "frac_over_1000m": round(sum(1 for e in edges if e["length_m"] > 1000) / len(edges), 4),
            "frac_over_2000m": round(sum(1 for e in edges if e["length_m"] > 2000) / len(edges), 4),
        }

    payload = {
        "type": "post_mortem_diagnostic",
        "status": "READ-ONLY replay of frozen scenarios. Not an experiment, no new claim.",
        "sample_size": len(records),
        "sampled_from": f"{len(partitioned)} partitioned scenarios (pre-registered set)",
        "summary": {"I1_route_resilience": summarise(i1e, "I1"),
                    "I3_nearest_gap": summarise(i3e, "I3")},
        "records": records,
    }
    path = os.path.join(RESULTS, "postmortem_i1_vs_i3.json")
    with open(path, "w") as f:
        json.dump(payload, f, indent=1)

    for k, v in payload["summary"].items():
        print(f"\n=== {k} ===")
        for kk, vv in v.items():
            print(f"  {kk:34s} {vv}")
    print(f"\nwrote {path}")


if __name__ == "__main__":
    main()
