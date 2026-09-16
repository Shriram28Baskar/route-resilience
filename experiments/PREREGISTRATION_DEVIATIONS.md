# Deviations from the P2 design, and errors in the design itself

Recorded as they were discovered, before results were interpreted. D8–D11 were
added after a post-publication adversarial audit and are labelled as such.

> **There is no pre-registration document in this repository.** The design that
> D1–D7 deviate *from* was never committed. F7 and F8 exist only as docstrings
> inside the scripts that test them; F1–F6 do not exist anywhere. What IS
> verifiable from git is the freeze ORDER: `experiments/scenarios/*.json` landed
> in commit `2ffc871` (2026-09-15), every result file in `5f3b9f2` (2026-09-16).
> Every other use of the word "pre-registered" in this repository should be read
> as "frozen before the run", not as "registered against a published protocol".
> A reviewer cannot check the analysis against a plan, because the plan is not
> here.

---

## D1 — S1/S2 scenario families omitted (planned)

The design specified five scenario families. S1 (observed flood failure set) and
S2 (bootstrap resamples of it) both require flood ground truth, which the
instruction explicitly deferred. Only **S3 (random-k), S4 (spatial-k) and
S5 (targeted-k)** were run. No scenario in this experiment represents a real
event.

## D2 — No real road graph (environmental blocker)

`overpass-api.de:443` is denied by this environment's network policy. The
Bengaluru OSM extract could not be fetched. Consequences:

> **D2 IS SUBSTANTIALLY WRONG — see D9.** `overpass-api.de:443` is indeed blocked,
> but a real Bengaluru Overpass response is committed in this repository and the
> real road graph rebuilds from it offline. The experiments below genuinely did
> not use it; the *reason* given for not using it was false.

* **A5** ran on the *topology proxy* — the node and edge set reconstructed from
  the committed edge-betweenness cache keys, with **uniform placeholder weights
  and no coordinates**. It is not the Bengaluru road graph. It is used only
  because k-sampling error is a function of graph size and structure, which the
  object does preserve. Synthetic graphs with *heterogeneous* weights were run
  alongside specifically to test whether the uniform-weight limitation changes
  the verdict.
* **P2.2** ran on synthetic graph families with real coordinates and geometric
  edge lengths, because budget-matching is denominated in metres and the proxy
  has no geometry. The proxy is therefore **excluded** from the intervention
  experiment.
* **A7** could not be run at city scale for the same reason. F7 is tested only
  up to ~500 nodes.

No Bengaluru measurement is claimed anywhere in this experiment.

## D3 — **F8's threshold was the wrong statistic. This is an error in my design, not a result.**

F8 was pre-registered as:

> Spearman rho between the k=5 ranking and exact betweenness < 0.7
> => production configuration invalid

This is a poor criterion and I should not have written it. Spearman rho over
*all* nodes is dominated by the large mass of low-centrality nodes, which any
sampling scheme ranks correctly near zero. A road network has a long tail of
degree-2 nodes with near-zero betweenness; getting those right inflates rho
regardless of whether the head of the ranking is correct.

**The product does not display the full ranking. It displays the top-K
"gatekeeper" list.** The statistic that matters for the deployed behaviour is
therefore **top-K overlap with exact betweenness**, which was collected as a
secondary metric.

Both are reported. The pre-registered F8 verdict is reported *as specified*, and
separately I report what the top-K evidence shows. **The pre-registered
threshold is not moved after seeing results.** Any future pre-registration for
this system should use top-K overlap (or rank-biased overlap) as the primary
criterion for a ranking that is consumed top-down.

## D4 — "Oracle" (I5) is neither an oracle, an upper bound, nor headroom

I5 searches a deterministic pool of at most 15 candidate edges (shortest-first,
drawn from the top-12 highest-degree nodes of the two largest components) and
selects the best **single** edge. Every other method may buy several edges within
the same budget.

**Correction (post-audit).** This entry previously called I5 "an **upper bound on
what this candidate family can achieve**" that "establishes headroom, not
optimality." Both are wrong, and the committed raw records refute them: I3 beats
I5 in **55 / 78 / 79** of 1,212 pre-registered scenarios at 500 / 1000 / 2000 m;
I1 beats it **17–9** at 2000 m (Wilcoxon p = 0.62); I2-random beats it 19 times.
It bounds nothing.

Read I5 as exactly what it is: **the best single edge from a bounded
15-candidate pool.** The method key `I5_oracle` is left unchanged in the raw
records so they stay joinable — the name is wrong, the data is not.

## D5 — I1's internal length assumption differs from the budget charged

`ablate_prescribe` assigns its proposed bridges a hardcoded `length=750 m`
(or 500 m for parallel links) regardless of the actual geometry between the
endpoints. The experiment charges the **true great-circle length** against the
budget, because charging the algorithm's own assumption would let it buy a 3 km
bridge for 750 m of budget. This is a fair-comparison decision, and it also
documents a real modelling flaw in the algorithm.

## D6 — `radial_25` is uninformative, retained anyway

The 25-node radial graph has two ring roads and is too redundant for any
k ∈ {5} disruption to partition it, so every method scores Δ = 0. The cell is
retained and reported rather than dropped, because dropping graph families on
which the method shows no effect is exactly how a result gets flattered.

## D7 — Second scenario set added at size-relative stress (declared post-hoc)

**Discovered mid-run, before any method comparison was interpreted.**

The pre-registered absolute-k set (k ∈ {5, 10, 20}) left redundant graphs
completely unpartitioned: **0 of the first 60 grid_400 scenarios produced more
than one component**, so every method scored exactly Δ = 0. That is not a
finding about the methods; it is a finding that the stressor was too weak to
create anything for an intervention to repair.

Response, in this order:

1. The pre-registered set runs to completion and is reported **in full**,
   including its null cells. It is not discarded.
2. A **second, separately frozen** set is added at size-relative stress,
   k ∈ {5%, 10%, 20%} of nodes, and reported separately and explicitly as a
   post-hoc extension.

This changes the *stressor*, never the method under test, and no intervention
algorithm was modified. It is still a deviation from the design and is labelled
as one wherever its results appear. Conclusions drawn from the relative-k set
carry weaker evidential weight than those from the pre-registered set.

Frozen artifacts:

* `scenarios/scenarios.json`          1212 scenarios, sha256 `c222fbd2e9b5…` (pre-registered)
* `scenarios/scenarios_relative.json` 1515 scenarios, sha256 `2e8dd6747a4f…` (post-hoc)

## D8 — 101 duplicate scenarios in the relative set (discovered by audit)

`radial_25` has 25 nodes, so `max(2, round(f * 25))` maps the fractions
{0.05, 0.10, 0.20} to k ∈ {2, **2**, 5}. **k=2 was generated twice**, producing
101 byte-identical duplicate scenario records.

* `scenarios_relative.json`: **1,515 records / 1,414 unique scenario_ids.**
  Earlier text in this file said "1515 scenarios" and RESEARCH_CLOSURE.md said
  "1,414" — both describe the same file, neither disclosed the duplication.
* `interventions_raw_relative.jsonl`: **24,240 raw rows / 22,624 unique**
  (1,414 × 16). All 1,616 duplicate rows verified byte-identical.
* `07_aggregate.py` deduplicated in the *paired comparisons* (dict-keyed on
  scenario_id → n=1,414) but **not** in the descriptive tables (→ n=1,515), so a
  single JSON file reported two different sample sizes. Every duplicated scenario
  is `radial_25`, which D6 records as always Δ=0, so the bias pulled medians
  toward 0 and inflated tie fractions — conservative in direction, wrong in n.

**Fixed:** the generator now deduplicates the k list; `07_aggregate.py` drops
exact duplicate rows (refusing to proceed if any duplicate pair disagrees) and
reports `record_counts` explicitly. The frozen scenario file and the raw JSONL
are **unchanged** — they are evidence.

## D9 — "no real road graph is available" was FALSE (discovered by audit)

`backend/cache/befdaed17dcd4b1967a71e322ded5946f4da89e1.json` — 6.0 MB,
git-tracked since the initial commit `f015407` — is a genuine Overpass API
response (Overpass 0.7.62.11, `timestamp_osm_base` 2026-06-16, 39,264 nodes /
12,135 ways, bbox 12.90665–12.99830 N / 77.55759–77.65045 E). OSMnx 1.9.3 is
installed with `settings.cache_folder = './cache'` and `use_cache = True`, so
`graph_from_bbox(12.92–12.99, 77.57–77.64)` **builds a connected 13,486-node /
19,117-edge Bengaluru road graph with real coordinates, offline**, verified with
sockets disabled.

Consequences:

1. D2's stated blocker was wrong. The port is blocked; the data is present.
2. The "topology proxy" was never necessary. It has the same node and edge counts
   as the real graph, minus the weights and coordinates.
3. The withdrawn README figures "13,486 intersections" and "16,000+ road
   segments" are **reproducible** and were over-withdrawn.
4. POSTMORTEM_H2 §5 gate G1 is **cleared**.

**None of A5, A7 or P2.2 used this graph.** Re-running any of them against it is
a **NEW EXPERIMENT**, has not been performed, and must not be performed merely to
obtain a better-looking number. The graph's existence is a documentation
correction, not a research result.

## D10 — duplicate ablation signatures in the PRE-REGISTERED set

The absolute set contains **77 distinct `(graph, family, ablated-node-set)`
signatures that occur more than once**, totalling **121 excess records** (10.0% of
1,212): ring_of_cliques_48 27, radial_25 16, grid_400 12, geometric_497 12,
chokepoint_196 10. These arise because different `(family, k, replicate)` cells
can draw the same node set on small graphs. They are **not independent
observations**, which the Wilcoxon signed-rank test and the bootstrap both assume.
Not corrected: correcting it would change the pre-registered analysis after the
fact. Disclosed here so a reviewer can discount accordingly.

## D11 — the design is unbalanced by family

Per `(graph, k)` cell: S3_random 50 replicates, S4_spatial 50, **S5_targeted 1**
(the family is deterministic, so replicates would be identical). The family
stratification in `07_aggregate.py` therefore compares n=50 cells against n=1
cells. Reported as-is; not disclosed in the original write-up.
