#!/usr/bin/env python3
"""
P2.2 step 1 — generate and FREEZE disruption scenarios.

Scenarios are written and hashed BEFORE any intervention code runs, so the
intervention evaluation cannot be tuned to the disruptions it will face.

SCENARIO FAMILIES (S1/S2 omitted: they require flood ground truth, not collected)
    S3  random-k        i.i.d. uniform node removal
    S4  spatial-k       seed a node, remove its k nearest neighbours by
                        great-circle distance. Flood-like blobs. i.i.d. removal
                        is a strawman that flatters any targeting method.
    S5  targeted-k      top-k by betweenness (worst case)

GRAPHS
    Synthetic families with REAL coordinates and geometric edge lengths, because
    the intervention experiment budget-matches on metres and the only
    Bengaluru-derived object available (the topology proxy) has no coordinates.
    No graph here is claimed to be Bengaluru.

OUTPUT
    experiments/scenarios/scenarios.json  + SHA256 recorded in the file itself
"""
from __future__ import annotations

import hashlib
import json
import math
import os
import random
import sys
from typing import Dict, List

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))

import networkx as nx

OUT_DIR = os.path.join(os.path.dirname(__file__), "scenarios")
MASTER_SEED = 20260915
K_VALUES = [5, 10, 20]
N_PER_CELL = 50

# Size-relative stress levels, added AFTER the absolute-k set was found to leave
# redundant graphs unpartitioned (see PREREGISTRATION_DEVIATIONS.md D7).
K_FRACTIONS = [0.05, 0.10, 0.20]


# ── geometry ──────────────────────────────────────────────────────────────────

def haversine_m(lat1, lon1, lat2, lon2) -> float:
    R = 6_371_000.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp = p2 - p1
    dl = math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * R * math.asin(math.sqrt(max(0.0, a)))


def _finalise(G: nx.Graph, label: str) -> nx.Graph:
    """Attach geometric lengths and travel times derived from coordinates."""
    for u, v in G.edges():
        du, dv = G.nodes[u], G.nodes[v]
        length = haversine_m(du["y"], du["x"], dv["y"], dv["x"])
        length = max(length, 1.0)
        speed = 30.0
        G.edges[u, v].update(length=length, weight=length, speed_kph=speed,
                             time_s=length / (speed * 1000 / 3600),
                             highway="residential")
    G.graph["label"] = label
    return G


# ── graph families ────────────────────────────────────────────────────────────
# Spacing ~100 m so a 500-2000 m intervention budget is a meaningful constraint.

DEG_PER_M_LAT = 1.0 / 111_320.0


def g_grid(side: int = 20) -> nx.Graph:
    G = nx.convert_node_labels_to_integers(nx.grid_2d_graph(side, side))
    for i, n in enumerate(sorted(G.nodes())):
        G.nodes[n]["y"] = 12.92 + (i // side) * 100 * DEG_PER_M_LAT
        G.nodes[n]["x"] = 77.57 + (i % side) * 100 * DEG_PER_M_LAT / math.cos(math.radians(12.95))
    return _finalise(G, "grid_400")


def g_chokepoint() -> nx.Graph:
    G = nx.Graph()
    blocks = []
    for b in range(4):
        B = nx.convert_node_labels_to_integers(nx.grid_2d_graph(7, 7), first_label=b * 100)
        G.add_edges_from(B.edges())
        blocks.append(sorted(B.nodes()))
    for b in range(3):
        G.add_edge(blocks[b][-1], blocks[b + 1][0])
    for b, blk in enumerate(blocks):
        for i, n in enumerate(blk):
            G.nodes[n]["y"] = 12.92 + (i // 7) * 100 * DEG_PER_M_LAT
            G.nodes[n]["x"] = (77.57 + (b * 900 + (i % 7) * 100)
                               * DEG_PER_M_LAT / math.cos(math.radians(12.95)))
    G.graph["bridge_nodes"] = [blocks[b][-1] for b in range(3)] + [blocks[b + 1][0] for b in range(3)]
    return _finalise(G, "chokepoint_196")


def g_ring_of_cliques() -> nx.Graph:
    G = nx.Graph()
    ncl, sz = 8, 6
    for c in range(ncl):
        C = nx.convert_node_labels_to_integers(nx.complete_graph(sz), first_label=c * 10)
        G.add_edges_from(C.edges())
        ang = 2 * math.pi * c / ncl
        for i, n in enumerate(sorted(C.nodes())):
            r = 800 + (i % 3) * 80
            G.nodes[n]["y"] = 12.92 + (r * math.sin(ang) + (i // 3) * 60) * DEG_PER_M_LAT
            G.nodes[n]["x"] = (77.57 + (r * math.cos(ang) + (i % 3) * 60)
                               * DEG_PER_M_LAT / math.cos(math.radians(12.95)))
    for c in range(ncl):
        G.add_edge(c * 10 + sz - 1, ((c + 1) % ncl) * 10)
    return _finalise(G, "ring_of_cliques_48")


def g_geometric(n: int = 500, seed: int = 3) -> nx.Graph:
    G = nx.random_geometric_graph(n, radius=0.075, seed=seed)
    lcc = max(nx.connected_components(G), key=len)
    G = nx.convert_node_labels_to_integers(G.subgraph(lcc).copy())
    for n_ in G.nodes():
        px, py = G.nodes[n_]["pos"]
        G.nodes[n_]["y"] = 12.92 + py * 2500 * DEG_PER_M_LAT
        G.nodes[n_]["x"] = 77.57 + px * 2500 * DEG_PER_M_LAT / math.cos(math.radians(12.95))
        del G.nodes[n_]["pos"]
    return _finalise(G, f"geometric_{G.number_of_nodes()}")


def g_radial() -> nx.Graph:
    """Hub-and-spoke with two ring roads — a common real city morphology."""
    G = nx.Graph()
    rings, spokes = 3, 8
    nid = 0
    ring_nodes = []
    for r in range(rings):
        this = []
        for s in range(spokes):
            ang = 2 * math.pi * s / spokes
            rad = 400 * (r + 1)
            G.add_node(nid,
                       y=12.92 + rad * math.sin(ang) * DEG_PER_M_LAT,
                       x=77.57 + rad * math.cos(ang) * DEG_PER_M_LAT / math.cos(math.radians(12.95)))
            this.append(nid)
            nid += 1
        for s in range(spokes):
            G.add_edge(this[s], this[(s + 1) % spokes])
        ring_nodes.append(this)
    G.add_node(nid, y=12.92, x=77.57)
    centre = nid
    for s in range(spokes):
        G.add_edge(centre, ring_nodes[0][s])
        for r in range(rings - 1):
            G.add_edge(ring_nodes[r][s], ring_nodes[r + 1][s])
    return _finalise(G, "radial_25")


FAMILIES = {f.__name__: f for f in (g_grid, g_chokepoint, g_ring_of_cliques,
                                    g_geometric, g_radial)}


# ── scenario construction ─────────────────────────────────────────────────────

def s3_random(G, k, rng) -> List:
    return rng.sample(sorted(G.nodes()), k)


def s4_spatial(G, k, rng) -> List:
    """Seed a node, take its k nearest neighbours by great-circle distance."""
    nodes = sorted(G.nodes())
    seed_node = rng.choice(nodes)
    sy, sx = G.nodes[seed_node]["y"], G.nodes[seed_node]["x"]
    ranked = sorted(nodes, key=lambda n: haversine_m(sy, sx, G.nodes[n]["y"], G.nodes[n]["x"]))
    return ranked[:k]


def s5_targeted(G, k, rng, bc_cache={}) -> List:
    label = G.graph["label"]
    if label not in bc_cache:
        bc_cache[label] = nx.betweenness_centrality(G, normalized=True, weight="weight", seed=42)
    bc = bc_cache[label]
    return [n for n, _ in sorted(bc.items(), key=lambda x: x[1], reverse=True)[:k]]


GENERATORS = {"S3_random": s3_random, "S4_spatial": s4_spatial, "S5_targeted": s5_targeted}


def main():
    os.makedirs(OUT_DIR, exist_ok=True)
    mode = sys.argv[1] if len(sys.argv) > 1 else "absolute"
    assert mode in ("absolute", "relative")
    payload: Dict = {
        "master_seed": MASTER_SEED,
        "mode": mode,
        "k_values": K_VALUES if mode == "absolute" else K_FRACTIONS,
        "n_per_cell": N_PER_CELL,
        "note": ("S1/S2 (observed flood scenarios) are ABSENT: flood ground truth "
                 "has not been collected. No scenario here represents a real event."),
        "graphs": {},
        "scenarios": [],
    }

    for fname, fn in FAMILIES.items():
        G = fn()
        label = G.graph["label"]
        payload["graphs"][label] = {
            "generator": fname,
            "nodes": G.number_of_nodes(),
            "edges": G.number_of_edges(),
            "connected": nx.is_connected(G),
            "total_edge_length_m": round(sum(d["length"] for _, _, d in G.edges(data=True)), 1),
        }
        k_list = (K_VALUES if mode == "absolute"
                  else [max(2, int(round(f * G.number_of_nodes()))) for f in K_FRACTIONS])
        for sname, gen in GENERATORS.items():
            for k in k_list:
                if k >= G.number_of_nodes() // 2:
                    continue
                for i in range(N_PER_CELL):
                    seed = MASTER_SEED + hash((label, sname, k, i)) % 10_000_019
                    rng = random.Random(seed)
                    nodes = gen(G, k, rng)
                    if sname == "S5_targeted" and i > 0:
                        continue          # deterministic: one scenario per (graph,k)
                    payload["scenarios"].append({
                        "scenario_id": f"{label}|{sname}|k{k}|{i}",
                        "graph": label, "family": sname, "k": k, "replicate": i,
                        "seed": seed,
                        "ablated_nodes": [str(n) for n in nodes],
                    })
        print(f"  {label}: {G.number_of_nodes()}n {G.number_of_edges()}e")

    body = json.dumps(payload, indent=1, sort_keys=True)
    digest = hashlib.sha256(body.encode()).hexdigest()
    payload["sha256_of_body"] = digest
    path = os.path.join(OUT_DIR,
                        "scenarios.json" if mode == "absolute" else "scenarios_relative.json")
    with open(path, "w") as f:
        json.dump(payload, f, indent=1, sort_keys=True)
    print(f"\n{len(payload['scenarios'])} scenarios -> {path}")
    print(f"sha256(body) {digest}")


if __name__ == "__main__":
    main()
