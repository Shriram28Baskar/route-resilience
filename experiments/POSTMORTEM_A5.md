# A5: global Spearman ρ substantially overstates top-K agreement at production k=5

Recorded because the discrepancy is a methodological trap, not just a finding
about this system. Evidence: `results/a5_k_sensitivity_proxy.json`
(sha256 `d2ff66ba1e28…`) and `results/a5_k_sensitivity_synth.json`.

---

## The setting

`app/api/graph.py` caps betweenness sampling at **k = 5 pivots** when a graph
exceeds 5000 nodes:

```python
effective_k = min(k, 5) if n > 5000 else k
```

Every criticality ranking the system serves for a city-scale network comes from
a 5-pivot approximation. A5 asked whether that ranking resembles exact
betweenness.

## The result

13,486-node topology proxy, 5 seeds per k, exact betweenness = 504.6 s:

| k | Spearman ρ (mean) | ρ (min) | top-5 | top-10 | top-20 | top-50 | runtime |
|---|---|---|---|---|---|---|---|
| **5 (production)** | **0.957** | 0.885 | 0.28 | **0.34** | 0.37 | 0.43 | 0.20 s |
| 25 | 0.983 | 0.980 | 0.32 | 0.54 | 0.78 | 0.79 | 0.96 s |
| 50 | 0.980 | 0.977 | 0.52 | 0.64 | 0.88 | 0.85 | 1.98 s |
| 100 | 0.975 | 0.971 | 0.72 | 0.78 | 0.93 | 0.91 | 3.87 s |
| 500 | 0.968 | 0.966 | 0.88 | 0.86 | 0.94 | 0.92 | 19.3 s |
| 1000 | 0.971 | 0.970 | 1.00 | 0.94 | 0.95 | 0.98 | 37.6 s |

Reproduced on heterogeneous-weight synthetic graphs (1,600 and 4,000 nodes):
ρ = 0.90–0.94 at k=5 with top-10 overlap 0.18–0.20.

## The trap

**ρ is flat across k (0.957 → 0.983) while top-10 overlap climbs 0.34 → 0.94.**

ρ is computed over every node. A road network is mostly degree-2 junctions with
near-zero betweenness, and *any* sampling scheme ranks those correctly — they
are all approximately tied at the bottom. That large, easy mass dominates the
rank correlation and leaves it insensitive to whether the head of the ranking is
right.

The head is the only part the product exposes. `/graph/criticality` returns a
top-N gatekeeper list; the dashboard renders it as the network's most critical
junctions. At k=5, **top-10 overlap with exact averages 0.34 and ranges [0.10,
0.60] across seeds** — between four and nine of the ten junctions shown as most
critical are not in the true top ten. ρ = 0.96 conceals this completely.

## Consequence for the pre-registration

F8 was pre-registered as "ρ(k=5, exact) < 0.7 ⇒ production configuration
invalid". It is **not triggered**: ρ is 0.885–0.977.

**The criterion was wrong, and that is an error in the experiment design, not a
property of the system.** The threshold has not been moved after seeing results;
both verdicts are reported (deviation D3). The lesson generalises:

> When a ranking is consumed top-down, validate it with a top-K statistic
> (top-K overlap, rank-biased overlap, NDCG). A global rank correlation over a
> long tail of ties will pass while the exposed portion of the ranking is wrong.

## Secondary observation

Exact betweenness costs 504 s at 13,486 nodes and 107 s at 4,000 nodes. The
k=5 cap is commented "to prevent timeouts", but `app/main.py` already
precomputes centrality in a startup background thread and persists it to disk
via the fingerprint-keyed cache. There is no latency argument for a 5-pivot
approximation of a metric that is computed once and cached.

**Not acted on.** Changing it is outside P2.0/P2.2 scope and would alter the
system while an evaluation of it is on record. It is logged here as a candidate
change for whoever picks up the next phase.
