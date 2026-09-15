# Deviations from the P2 design, and errors in the design itself

Recorded as they were discovered, before results were interpreted.

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

## D4 — Oracle (I5) is a bounded greedy search, not a true optimum

I5 searches a deterministic pool of at most 15 candidate edges (shortest-first,
drawn from the highest-degree nodes of the two largest components). It is an
**upper bound on what this candidate family can achieve**, not a global optimum
over all possible edges. Reported as such; it establishes headroom, not
optimality.

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
