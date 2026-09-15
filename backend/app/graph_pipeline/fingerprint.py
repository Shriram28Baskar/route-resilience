"""
Deterministic graph fingerprinting.

Centrality computation on a 13k-node road network is expensive, so results are
cached to disk. Before this module the cache was keyed only on a boolean flag
(`G.graph["is_osm_fallback"]`), which meant a cache computed for one AOI was
returned verbatim for any other graph carrying that flag — silently, with zero
node overlap.

A fingerprint is derived from the graph's identity (node IDs, edge set),
the AOI bounding box it was cut from, and the edge weights that centrality
actually depends on. Any change to those inputs changes the fingerprint, so a
stale cache is detected rather than trusted.

Fingerprints are stable across processes and Python versions: everything is
canonicalised to sorted text before hashing. Node attributes that carry
float noise (coordinates) are excluded; the topology and the routing weights
are what centrality is a function of.
"""
from __future__ import annotations

import hashlib
import json
import os
from typing import Any, Dict, Optional

import networkx as nx

# Bump when the hashing scheme changes, so old caches are invalidated.
FINGERPRINT_SCHEMA_VERSION = "1"

# Edge attributes centrality/routing actually consume.
_WEIGHT_KEYS = ("weight", "length", "time_s")


def _canonical_node(n: Any) -> str:
    return repr(n)


def _round_weight(v: Any) -> str:
    """Quantise weights so float jitter does not churn the fingerprint."""
    try:
        return f"{float(v):.6g}"
    except (TypeError, ValueError):
        return "na"


def graph_fingerprint(G: Optional[nx.Graph]) -> Optional[str]:
    """
    Return a stable hex digest identifying this graph's topology + weights.

    Returns None for a null graph. Cheap relative to centrality (single pass),
    but not free: callers should compute it once per request, not per node.
    """
    if G is None:
        return None

    h = hashlib.sha256()
    h.update(f"v{FINGERPRINT_SCHEMA_VERSION}\n".encode())
    h.update(f"n={G.number_of_nodes()};e={G.number_of_edges()};"
             f"multi={G.is_multigraph()};directed={G.is_directed()}\n".encode())

    # AOI provenance travels with the graph when it was cut from a bbox.
    aoi = G.graph.get("aoi_bbox")
    if aoi:
        h.update(("aoi=" + json.dumps(aoi, sort_keys=True) + "\n").encode())
    src = G.graph.get("source_id")
    if src:
        h.update(f"src={src}\n".encode())

    # Node identity only; coordinates are excluded (float noise, and centrality
    # does not read them).
    for n in sorted(G.nodes(), key=_canonical_node):
        h.update(_canonical_node(n).encode())
        h.update(b"|")
    h.update(b"\n--edges--\n")

    # Edge set plus the weights routing depends on, canonically ordered.
    rows = []
    if G.is_multigraph():
        for u, v, k, d in G.edges(keys=True, data=True):
            a, b = sorted((_canonical_node(u), _canonical_node(v)))
            rows.append(f"{a}~{b}~{k}~" +
                        ",".join(_round_weight(d.get(w)) for w in _WEIGHT_KEYS))
    else:
        for u, v, d in G.edges(data=True):
            a, b = sorted((_canonical_node(u), _canonical_node(v)))
            rows.append(f"{a}~{b}~" +
                        ",".join(_round_weight(d.get(w)) for w in _WEIGHT_KEYS))
    for r in sorted(rows):
        h.update(r.encode())
        h.update(b"|")

    return h.hexdigest()


def short_fingerprint(G: Optional[nx.Graph]) -> Optional[str]:
    fp = graph_fingerprint(G)
    return fp[:16] if fp else None


def describe_graph_source(G: Optional[nx.Graph]) -> Optional[Dict[str, Any]]:
    """
    Human-readable statement of exactly which graph artifact is being analysed.

    Everything returned here comes from attributes stamped onto the graph at
    construction time; nothing is inferred.
    """
    if G is None:
        return None
    return {
        "artifact": G.graph.get("artifact", "unknown"),
        "aoi_bbox": G.graph.get("aoi_bbox"),
        "osmnx_version": G.graph.get("osmnx_version"),
        "network_type": G.graph.get("network_type"),
        "downloaded_utc": G.graph.get("downloaded_utc"),
        "source_id": G.graph.get("source_id"),
        "fingerprint": graph_fingerprint(G),
        "fingerprint_schema": FINGERPRINT_SCHEMA_VERSION,
        "nodes": G.number_of_nodes(),
        "edges": G.number_of_edges(),
    }


class StaleCacheError(RuntimeError):
    """Raised when a cached artifact does not belong to the graph in hand."""


def verify_cache_fingerprint(cache: Dict[str, Any], G: nx.Graph,
                             cache_path: str, strict: bool) -> bool:
    """
    Check that `cache` was computed for `G`.

    Returns True when the cache is usable. When it is not:
      * strict=True  -> raise StaleCacheError (fail loudly)
      * strict=False -> return False so the caller recomputes

    An unkeyed legacy cache (no fingerprint field) is always rejected: it is
    exactly the failure mode this module exists to prevent.
    """
    expected = graph_fingerprint(G)
    found = cache.get("graph_fingerprint")

    if found == expected:
        return True

    reason = (
        "cache has no graph_fingerprint (pre-fingerprint artifact)"
        if found is None else
        f"fingerprint mismatch: cache={found[:16]}… graph={(expected or '')[:16]}…"
    )
    message = (
        f"Refusing to use centrality cache at {cache_path}: {reason}. "
        f"The cached scores were computed for a different graph and would be "
        f"silently wrong for this one."
    )
    if strict:
        raise StaleCacheError(message)
    return False


def strict_cache_mode() -> bool:
    """
    Whether a stale cache should raise instead of recompute.

    Default is False (recompute, log loudly) so a normal deployment self-heals.
    Set STRICT_GRAPH_CACHE=true in reproducibility runs and CI, where silently
    recomputing would mask a provenance error.
    """
    return os.getenv("STRICT_GRAPH_CACHE", "false").strip().lower() in ("1", "true", "yes")
