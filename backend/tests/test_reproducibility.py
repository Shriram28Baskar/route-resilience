"""
Reproducibility guarantees: graph fingerprinting, cache keying, state isolation,
and provenance reporting.

These protect the claim "this result came from this graph".
"""
import json
import os
import pickle

import networkx as nx
import pytest

from app.graph_pipeline.fingerprint import (
    FINGERPRINT_SCHEMA_VERSION,
    StaleCacheError,
    describe_graph_source,
    graph_fingerprint,
    verify_cache_fingerprint,
)
from app.graph_pipeline.graph_build import GraphStore


# ── fingerprint determinism and sensitivity ───────────────────────────────────

def test_fingerprint_is_deterministic(chokepoint):
    assert graph_fingerprint(chokepoint) == graph_fingerprint(chokepoint)


def test_fingerprint_is_insensitive_to_node_insertion_order():
    """Two graphs with identical topology must hash identically."""
    a = nx.Graph()
    a.add_edges_from([(1, 2), (2, 3), (3, 1)])
    b = nx.Graph()
    b.add_edges_from([(3, 1), (2, 3), (1, 2)])
    for G in (a, b):
        for u, v in G.edges():
            G.edges[u, v].update(weight=1.0, length=1.0, time_s=1.0)
    assert graph_fingerprint(a) == graph_fingerprint(b)


def test_fingerprint_changes_when_topology_changes(chokepoint):
    before = graph_fingerprint(chokepoint)
    G = chokepoint.copy()
    G.add_edge(0, 300, weight=1.0, length=1.0, time_s=1.0)
    assert graph_fingerprint(G) != before


def test_fingerprint_changes_when_routing_weights_change(chokepoint):
    """Centrality depends on weights, so the cache key must too."""
    before = graph_fingerprint(chokepoint)
    G = chokepoint.copy()
    u, v = next(iter(G.edges()))
    G.edges[u, v]["time_s"] = 999.0
    assert graph_fingerprint(G) != before


def test_fingerprint_changes_when_aoi_changes(chokepoint):
    before = graph_fingerprint(chokepoint)
    G = chokepoint.copy()
    G.graph["aoi_bbox"] = {"south": 0, "west": 0, "north": 1, "east": 1}
    assert graph_fingerprint(G) != before


def test_fingerprint_ignores_coordinate_jitter(chokepoint):
    """Float noise in display coordinates must not invalidate a valid cache."""
    before = graph_fingerprint(chokepoint)
    G = chokepoint.copy()
    for n in G.nodes():
        G.nodes[n]["x"] = G.nodes[n]["x"] + 1e-12
    assert graph_fingerprint(G) == before


# ── cache mismatch must not be silent ─────────────────────────────────────────

def test_mismatched_cache_is_refused(grid, chokepoint):
    cache = {"graph_fingerprint": graph_fingerprint(chokepoint), "betweenness": {}}
    assert verify_cache_fingerprint(cache, grid, "x.pickle", strict=False) is False
    with pytest.raises(StaleCacheError, match="fingerprint mismatch"):
        verify_cache_fingerprint(cache, grid, "x.pickle", strict=True)


def test_unkeyed_legacy_cache_is_refused(grid):
    """
    The committed criticality pickle has no fingerprint. It was returned for
    ANY graph carrying the is_osm_fallback flag: 13,486 scores for a 25-node
    graph, zero node overlap, no warning.
    """
    legacy = {"betweenness": {1: 0.5}, "closeness": {1: 0.5}}
    assert verify_cache_fingerprint(legacy, grid, "x.pickle", strict=False) is False
    with pytest.raises(StaleCacheError, match="no graph_fingerprint"):
        verify_cache_fingerprint(legacy, grid, "x.pickle", strict=True)


def test_matching_cache_is_accepted(chokepoint):
    cache = {"graph_fingerprint": graph_fingerprint(chokepoint), "betweenness": {}}
    assert verify_cache_fingerprint(cache, chokepoint, "x.pickle", strict=True) is True


@pytest.mark.parametrize("strict", [False, True])
def test_centrality_does_not_return_foreign_cached_scores(
    grid, monkeypatch, tmp_path, strict
):
    """
    End-to-end version of the failure above, through compute_betweenness.
    A 25-node graph must never receive 13k cached scores.

    Both cache modes are covered because they have different CORRECT outcomes:
      strict=False -> discard the foreign cache and recompute
      strict=True  -> raise, so a provenance error cannot be papered over
    """
    import app.graph_pipeline.centrality as C

    foreign = {"betweenness": {9_000_000 + i: 0.5 for i in range(13_486)}}
    cache_file = tmp_path / "criticality.pickle"
    cache_file.write_bytes(pickle.dumps(foreign))
    monkeypatch.setattr(C, "CRITICALITY_CACHE_PATH", str(cache_file))
    monkeypatch.setenv("STRICT_GRAPH_CACHE", "true" if strict else "false")
    C._centrality_cache.clear()

    small = grid.copy()
    small.graph["is_osm_fallback"] = True

    if strict:
        with pytest.raises(StaleCacheError):
            C.compute_betweenness(small, k=10)
        return

    scores = C.compute_betweenness(small, k=10)
    assert set(scores) <= set(small.nodes()), (
        "compute_betweenness returned scores for nodes that are not in the graph"
    )
    assert len(scores) == small.number_of_nodes()


def test_committed_criticality_pickle_is_rejected(grid):
    """
    The artifact shipped in this repository predates fingerprinting. It must be
    refused rather than silently trusted. Skipped if it has been removed.
    """
    path = os.path.join(os.path.dirname(__file__), "..", "data", "graphs",
                        "osm_fallback_criticality.pickle")
    if not os.path.exists(path):
        pytest.skip("criticality pickle not present")
    with open(path, "rb") as f:
        cache = pickle.load(f)
    if "graph_fingerprint" in cache:
        pytest.skip("pickle has been regenerated with a fingerprint")
    assert verify_cache_fingerprint(cache, grid, path, strict=False) is False


# ── graph source reporting ────────────────────────────────────────────────────

def test_graph_source_states_which_artifact_is_analysed(chokepoint):
    src = describe_graph_source(chokepoint)
    assert src["fingerprint"] == graph_fingerprint(chokepoint)
    assert src["fingerprint_schema"] == FINGERPRINT_SCHEMA_VERSION
    assert src["aoi_bbox"] is not None
    assert src["nodes"] == chokepoint.number_of_nodes()


# ── ML / analysis state isolation ─────────────────────────────────────────────

def test_ml_pipeline_cannot_mutate_the_analysis_graph(chokepoint):
    """
    /graph/heal previously wrote the global analysis graph, so uploading any
    tile on /explain silently replaced the network every other endpoint used.
    """
    import base64
    import io

    import numpy as np
    from PIL import Image

    import app.api.graph as gapi

    GraphStore.set_healed(chokepoint)
    before = GraphStore.get_healed().number_of_nodes()

    mask = np.zeros((96, 96), np.uint8)
    mask[45:50, :] = 255
    mask[:, 45:50] = 255
    buf = io.BytesIO()
    Image.fromarray(mask).save(buf, format="PNG")
    gapi.build_graph({"mask_b64": base64.b64encode(buf.getvalue()).decode()})
    gapi.heal_road_graph()

    assert GraphStore.get_healed().number_of_nodes() == before, (
        "the segmentation pipeline replaced the analysis graph"
    )
    assert GraphStore.get_ml_healed() is not None
    assert GraphStore.get_ml_healed().number_of_nodes() != before


def test_graph_store_slots_are_distinct(chokepoint, grid):
    GraphStore.set_healed(chokepoint)
    GraphStore.set_ml_healed(grid)
    assert GraphStore.get_healed().number_of_nodes() == chokepoint.number_of_nodes()
    assert GraphStore.get_ml_healed().number_of_nodes() == grid.number_of_nodes()


# ── provenance ────────────────────────────────────────────────────────────────

def test_missing_artifact_yields_503_not_a_number():
    """A missing input must never be answered with a substitute value."""
    from fastapi import HTTPException

    from app.provenance import measured

    prov = measured("od_matrix_csv")
    if prov.status != "unavailable":
        pytest.skip("od_matrix.csv is present in this deployment")
    with pytest.raises(HTTPException) as exc:
        prov.require_available("/simulate/traffic-impact")
    assert exc.value.status_code == 503
    assert exc.value.detail["error"] == "required_input_unavailable"


def test_assumptions_downgrade_status_to_derived(chokepoint):
    from app.provenance import DERIVED, MEASURED, Provenance, graph_input

    prov = Provenance(status=MEASURED)
    prov.inputs.append(graph_input(chokepoint))
    assert prov.status == MEASURED
    prov.assume("population_per_node = 1008")
    assert prov.status == DERIVED


def test_provenance_block_is_attached_to_responses(chokepoint):
    from app.api.simulation import CompareRequest, ablate_compare

    GraphStore.set_healed(chokepoint)
    body = json.loads(ablate_compare(CompareRequest(top_n=3)).body)
    prov = body["data_provenance"]
    assert prov["status"] in ("measured", "derived", "synthetic")
    assert any(i.get("kind") == "graph" for i in prov["inputs"])
    assert any(i.get("fingerprint") for i in prov["inputs"])


def test_flood_endpoint_refuses_without_a_dem(chokepoint):
    """The flood model degenerates to a global switch without a DEM."""
    from fastapi import HTTPException

    from app.api.simulation import FloodRequest, simulate_flood
    from app.provenance import artifact_present

    if artifact_present("dem"):
        pytest.skip("DEM present in this deployment")
    GraphStore.set_healed(chokepoint)
    with pytest.raises(HTTPException) as exc:
        simulate_flood(FloodRequest(water_level=900.0))
    assert exc.value.status_code == 503


def test_evacuation_endpoint_declares_itself_unimplemented(chokepoint):
    from fastapi import HTTPException

    from app.api.simulation import EvacuationRequest, run_evacuation

    GraphStore.set_healed(chokepoint)
    with pytest.raises(HTTPException) as exc:
        run_evacuation(EvacuationRequest(ablated_node_ids=[]))
    assert exc.value.status_code == 503
    assert exc.value.detail["error"] == "not_implemented"
