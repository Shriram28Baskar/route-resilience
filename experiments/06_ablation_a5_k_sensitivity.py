#!/usr/bin/env python3
"""
A5 — k-sample betweenness sensitivity.

QUESTION
    /graph/criticality caps the betweenness pivot count at k=5 for graphs with
    more than 5000 nodes (app/api/graph.py). Every criticality ranking served
    for a city-scale network therefore comes from a 5-pivot approximation.
    Is that ranking close to exact betweenness, or is it noise?

FAILURE CONDITION (pre-registered, F8)
    Spearman rho between the k=5 ranking and exact betweenness < 0.7
    => the production configuration is invalid and no downstream result that
       depends on it can be reported.

GRAPHS
    proxy_topology   13,486 nodes / 19,069 edges. Node and edge set of the
                     Bengaluru network, reconstructed from the committed
                     edge-betweenness cache KEYS. It has NO real lengths,
                     travel times, speeds or coordinates; every weight is a
                     uniform placeholder. It is NOT the Bengaluru road graph
                     and no result here is a measurement about Bengaluru.
                     It is used because k-sampling error is a function of graph
                     SIZE and STRUCTURE, which this object does preserve.

    synth_hetero_*   Synthetic graphs at comparable scale WITH heterogeneous
                     edge weights, included specifically to check whether the
                     uniform-weight limitation of the proxy changes the verdict.

OUTPUTS
    experiments/results/a5_k_sensitivity.json   raw per-cell records
"""
from __future__ import annotations

import hashlib
import json
import os
import pickle
import random
import sys
import time
from typing import Dict, List

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))

import networkx as nx
from scipy.stats import spearmanr, kendalltau

RESULTS = os.path.join(os.path.dirname(__file__), "results")
PROXY_PICKLE = os.path.join(os.path.dirname(__file__), "..", "backend",
                            "data", "graphs", "osm_fallback_criticality.pickle")

# Production settings under test (app/api/graph.py, app/graph_pipeline/centrality.py)
PRODUCTION_K_LARGE = 5      # applied when n > 5000
PRODUCTION_K_DEFAULT = 50
PRODUCTION_SEED = 42

K_VALUES = [5, 25, 50, 100, 200, 500, 1000]
SEEDS = [42, 1, 2, 3, 4]     # 42 is production; the rest measure seed variance
TOP_K = [5, 10, 20, 50, 100]


# ── graphs ────────────────────────────────────────────────────────────────────

def load_proxy_topology() -> nx.Graph:
    with open(PROXY_PICKLE, "rb") as f:
        cache = pickle.load(f)
    G = nx.Graph()
    for key in cache["edge_betweenness"]:
        G.add_edge(key[0], key[1])
    for u, v in G.edges():
        G.edges[u, v]["weight"] = 1.0        # uniform: no real lengths exist
    G.graph["label"] = "proxy_topology"
    G.graph["weights"] = "uniform_placeholder"
    return G


def synth_hetero(n_side: int, seed: int, label: str) -> nx.Graph:
    """Grid with a heterogeneous, seeded weight distribution."""
    G = nx.convert_node_labels_to_integers(nx.grid_2d_graph(n_side, n_side))
    rng = random.Random(seed)
    for u, v in G.edges():
        G.edges[u, v]["weight"] = rng.lognormvariate(4.6, 0.6)   # ~100m median
    G.graph["label"] = label
    G.graph["weights"] = "synthetic_lognormal"
    return G


def synth_hetero_sparse(n: int, seed: int, label: str) -> nx.Graph:
    """Sparse, road-like: low mean degree, heterogeneous weights."""
    rng = random.Random(seed)
    G = nx.random_geometric_graph(n, radius=0.028, seed=seed)
    lcc = max(nx.connected_components(G), key=len)
    G = G.subgraph(lcc).copy()
    for u, v in G.edges():
        G.edges[u, v]["weight"] = rng.lognormvariate(4.6, 0.6)
    G.graph["label"] = label
    G.graph["weights"] = "synthetic_lognormal"
    return G


# ── metrics ───────────────────────────────────────────────────────────────────

def top_k_overlap(a: Dict, b: Dict, k: int) -> float:
    ta = {n for n, _ in sorted(a.items(), key=lambda x: x[1], reverse=True)[:k]}
    tb = {n for n, _ in sorted(b.items(), key=lambda x: x[1], reverse=True)[:k]}
    return len(ta & tb) / k


def compare(approx: Dict, exact: Dict) -> Dict:
    nodes = sorted(exact.keys())
    va = [approx.get(n, 0.0) for n in nodes]
    ve = [exact[n] for n in nodes]
    rho, rho_p = spearmanr(va, ve)
    tau, tau_p = kendalltau(va, ve)
    return {
        "spearman_rho": round(float(rho), 6),
        "spearman_p": float(rho_p),
        "kendall_tau": round(float(tau), 6),
        "kendall_p": float(tau_p),
        **{f"top{k}_overlap": round(top_k_overlap(approx, exact, k), 4) for k in TOP_K},
    }


def assert_uniform_weight_equivalence(G: nx.Graph, k: int = 20) -> bool:
    """Verify the BFS/Dijkstra equivalence claim rather than asserting it."""
    a = nx.betweenness_centrality(G, k=k, normalized=True, weight=None, seed=99)
    b = nx.betweenness_centrality(G, k=k, normalized=True, weight="weight", seed=99)
    return all(abs(a[n] - b[n]) < 1e-12 for n in a)


def betweenness(G: nx.Graph, k, seed) -> tuple:
    """
    Return (scores, seconds). k=None means exact. Mirrors the production call in
    app/graph_pipeline/centrality.py (normalized=True, weight="weight").

    OPTIMISATION, not an approximation: when every edge weight is identical a
    weighted shortest path is hop-count x constant, so the shortest-path SET is
    the same as the unweighted one and betweenness is mathematically identical.
    networkx then uses BFS instead of Dijkstra, which is several times faster.
    Applied ONLY to graphs flagged uniformly weighted; heterogeneous graphs keep
    the weighted call. The equivalence is verified at runtime, not assumed.
    """
    uniform = G.graph.get("weights") == "uniform_placeholder"
    t0 = time.time()
    bc = nx.betweenness_centrality(G, k=k, normalized=True,
                                   weight=None if uniform else "weight", seed=seed)
    return bc, time.time() - t0


# ── run ───────────────────────────────────────────────────────────────────────

def run_graph(G: nx.Graph) -> Dict:
    label = G.graph["label"]
    n = G.number_of_nodes()
    print(f"\n=== {label}: {n} nodes, {G.number_of_edges()} edges "
          f"(weights={G.graph['weights']}) ===", flush=True)

    if G.graph.get("weights") == "uniform_placeholder":
        ok = assert_uniform_weight_equivalence(G)
        print(f"  uniform-weight BFS/Dijkstra equivalence verified: {ok}", flush=True)
        if not ok:
            raise SystemExit("equivalence check FAILED - refusing the fast path")

    print("  computing EXACT betweenness ...", flush=True)
    exact, t_exact = betweenness(G, None, None)
    print(f"  exact: {t_exact:.1f}s", flush=True)

    cells: List[Dict] = []
    for k in K_VALUES:
        if k >= n:
            continue
        for seed in SEEDS:
            approx, dt = betweenness(G, k, seed)
            m = compare(approx, exact)
            cells.append({"graph": label, "n": n, "k": k, "seed": seed,
                          "runtime_s": round(dt, 3), **m})
            tag = "  <-- PRODUCTION (n>5000)" if k == PRODUCTION_K_LARGE and seed == PRODUCTION_SEED else (
                  "  <-- production default" if k == PRODUCTION_K_DEFAULT and seed == PRODUCTION_SEED else "")
            print(f"  k={k:<5} seed={seed:<3} rho={m['spearman_rho']:+.4f} "
                  f"top10={m['top10_overlap']:.2f} top50={m['top50_overlap']:.2f} "
                  f"{dt:6.2f}s{tag}", flush=True)

    return {"graph": label, "n": n, "m": G.number_of_edges(),
            "weights": G.graph["weights"],
            "exact_runtime_s": round(t_exact, 2), "cells": cells}


def main():
    os.makedirs(RESULTS, exist_ok=True)
    which = sys.argv[1] if len(sys.argv) > 1 else "all"

    graphs = []
    if which in ("all", "proxy"):
        graphs.append(load_proxy_topology())
    if which in ("all", "synth"):
        graphs.append(synth_hetero(40, 7, "synth_grid_1600_hetero"))
        graphs.append(synth_hetero_sparse(4000, 11, "synth_geometric_4000_hetero"))

    out = [run_graph(G) for G in graphs]

    path = os.path.join(RESULTS, f"a5_k_sensitivity{'' if which=='all' else '_'+which}.json")
    payload = {
        "experiment": "A5_k_sensitivity",
        "failure_condition_F8": "spearman_rho(k=5, exact) < 0.7 => production config invalid",
        "production_settings": {
            "k_large_graphs": PRODUCTION_K_LARGE,
            "k_default": PRODUCTION_K_DEFAULT,
            "seed": PRODUCTION_SEED,
            "threshold_nodes": 5000,
        },
        "proxy_caveat": (
            "proxy_topology has the node/edge set of the Bengaluru network but "
            "uniform placeholder weights and no coordinates. It is NOT the "
            "Bengaluru road graph. No result here is a Bengaluru measurement."
        ),
        "results": out,
    }
    with open(path, "w") as f:
        json.dump(payload, f, indent=1)
    digest = hashlib.sha256(open(path, "rb").read()).hexdigest()
    print(f"\nwrote {path}\nsha256 {digest}")


if __name__ == "__main__":
    main()
