# Post-mortem: why Route Resilience lost to nearest-gap closure

P2.2 is frozen. Nothing in this document re-runs, re-tunes, or re-scopes the
experiment. It explains a result that has already been recorded.

All evidence below comes from the committed pre-registered raw output
(`interventions_raw.jsonl`, sha256 `05c4bd4e6ffa…`, 19,392 records / 1,212
scenarios) plus a deterministic replay of the two proposers on the same frozen
scenarios (`08_postmortem_i1_vs_i3.py` → `postmortem_i1_vs_i3.json`). The replay
recovers the edge endpoints, which the raw records did not store. Both proposers
are deterministic given (graph, ablated set, seed), so the replay reproduces
what already ran.

---

## 1. Mechanism

### 1.1 The two methods pick equally good endpoints

Over a 120-scenario replay (158 proposed edges each):

| | I1 Route Resilience | I3 nearest-gap |
|---|---|---|
| edges proposed | 158 | 158 |
| fraction bridging two components | **1.00** | **1.00** |
| median endpoint degree | **4.0** | **4.0** |
| median edge length | **1454.8 m** | **556.7 m** |
| mean edge length | 1445.0 m | 664.9 m |
| fraction > 500 m | 0.962 | 0.709 |
| fraction > 1000 m | 0.740 | 0.196 |

Both always bridge a genuine partition. Both select endpoints of identical
median degree. **I1's edges are ~2.6× longer.**

*(Corrected after the post-publication audit: the original text said "the only
material difference is that I1's edges are ~2.6× longer." That was wrong. There
is a second material difference — which components each method joins — and it is
documented in §1.6 below. The endpoint-degree medians tie at 4.0, but the
distributions do not: I1's endpoints span degrees {0,1,2,3,4,5,6,7,11,17},
I3's span {0,1,2,3,4,5,6,12,13,14}.)*

### 1.2 Why: the two proposers optimise different things

`ablate_prescribe` (I1) selects, for each pair of components:

```python
a_node = max(comp_a, key=lambda n: G_perturbed.degree(n))
b_node = max(comp_b, key=lambda n: G_perturbed.degree(n))
```

The highest-degree node in each fragment, **with no reference to geometry at
all**. On these graphs most nodes tie at the maximum degree, so `max()` returns
whichever the iteration order reaches first — the choice is effectively
arbitrary among tied nodes, and the expected endpoint separation is therefore
the *mean* inter-component distance.

`propose_nearest_gap` (I3) minimises `edge_length_m(G, u, v)` over the two
fragments, i.e. the *minimum* inter-component distance.

*(The claim that "most nodes tie at the maximum degree" was asserted, never
measured. The committed replay shows I1 endpoints at degrees 0 through 17, which
is not consistent with a uniform tie at the maximum. Treat the tie-breaking story
as **UNVERIFIED**; the length difference itself is measured and stands.)*

I1 effectively optimises **"connect the hubs"**. I3 effectively optimises
**"connect cheaply"**. Under a length budget only the second is aligned with the
constraint; I1 is solving an unconstrained problem inside a constrained one.

### 1.3 Consequence A — I1 is priced out

Partitioned scenarios (n=253). I1 produced a proposal in **253/253**, but:

| budget | proposed | actually afforded | priced out |
|---|---|---|---|
| 500 m | 253 | 8 | **245** |
| 1000 m | 253 | 88 | **165** |
| 2000 m | 253 | 222 | 31 |

Its median proposal (1455 m) is almost 3× the 500 m budget.

### 1.4 Consequence B — even when affordable, I1 still never wins

Restricting to scenarios where **both** methods added at least one edge:

| budget | n | I1 median Δ | I3 median Δ | I1 wins | I3 wins | ties |
|---|---|---|---|---|---|---|
| 500 m | 8 | 0.0059 | 0.0262 | 0 | 2 | 6 |
| 1000 m | 88 | 0.0372 | 0.1259 | 0 | 32 | 56 |
| 2000 m | 222 | 0.1401 | 0.2172 | **0** | 48 | 174 |

So affordability is not the whole story. The second mechanism:

### 1.5 The decisive fact — Δ is invariant to *which* endpoints are chosen

At 2000 m, among scenarios where both acted, outcome by edge count:

| I1 edges | I3 edges | winner | count |
|---|---|---|---|
| 1 | 1 | **tie** | 167 |
| 2 | 2 | tie | 7 |
| 2 | 2 | I3 | 5 |
| 1 | 2 | I3 | 41 |
| 1 | 3 | I3 | 1 |
| 2 | 3 | I3 | 1 |

**When both methods add the same number of edges the result is a tie in 174 of
179 cases (97%). Of I3's 48 wins, 43 (89.6%) involved buying more edges — and 5
did not.**

> **Correction.** This paragraph previously read "Every case I3 wins is a case
> where it bought more edges (43/43)." That contradicted the table immediately
> above it, which records `I1 edges = 2 | I3 edges = 2 | winner I3 | count 5`.
> I3 won **48** times, not 43. The five same-edge-count wins are not noise: they
> are the signature of the mechanism in §1.6.

This is not an empirical accident; it follows from the definition of the
objective. `unreachable_fraction` counts origin–destination pairs that were
reachable in the baseline and are not reachable after the disruption. Joining
components A and B restores **exactly the pairs that straddle A and B**, and
that set is identical regardless of which node of A is wired to which node of B.
Any bridging edge, anywhere, restores the same OD pairs.

Therefore, under Δ unreachable_fraction, **given the same pair of components
joined**:

* **which node of A is wired to which node of B is worth nothing** — and that is
  the quantity I1 optimises;
* **edge cost is worth a great deal** — it determines how many component-pairs
  fit inside the budget.

Note the qualifier. The invariance holds *conditional on the component pair*.
**Which components get joined is not invariant, and that is a separate lever that
I1 also gets wrong** — see §1.6. The original version of this document stated the
invariance without the qualifier and concluded that endpoint choice is
universally irrelevant. That overstates it, and the 5 same-edge-count losses in
§1.5 are the counterexamples.

---

## 1.6 The second mechanism — chain vs. star (added after the audit)

The two proposers do not target the same components.

`ablate_prescribe` (I1), partitioned branch:

```python
comps_sorted = sorted(comps, key=len, reverse=True)
for i in range(min(req.max_recommendations, len(comps_sorted) - 1)):
    comp_a = comps_sorted[i]          # <-- i, not 0
    comp_b = comps_sorted[i + 1]
```

`propose_nearest_gap` (I3):

```python
for i in range(min(3, len(comps) - 1)):
    a, b = list(comps[0]), list(comps[i + 1])   # <-- always comps[0]
```

I1 builds a **chain** (0–1, 1–2, 2–3). I3 builds a **star** centred on the giant
component (0–1, 0–2, 0–3). Measured over the 120-scenario replay, by component
index:

| | (0,1) | (1,2) | (2,3) | (0,2) | (0,3) | edges touching comp 0 |
|---|---|---|---|---|---|---|
| I1 | 120 | 25 | 13 | 0 | 0 | **120/158 = 75.9%** |
| I3 | 120 | 0 | 0 | 25 | 13 | **158/158 = 100%** |

With a full budget the two are equivalent — a chain and a star over the same
component set both merge it. **Under a partial budget they are not.**
`apply_budget` skips an unaffordable proposal and continues to the next, so I1
can end up buying only its 2nd or 3rd edge, which under the chain design joins
two *minor* fragments and leaves the giant component untouched. An I3 edge always
reattaches a fragment to the giant component and therefore always restores the
larger set of OD pairs.

This is the mechanism behind the 5 same-edge-count losses in §1.5, and it is
independent of edge length. It was missed in the first version of this
post-mortem, which attributed the entire result to cost.

---

## 2. What the experiment falsified

**Falsified:** that Route Resilience's prescriptive layer produces better
interventions than **the strongest** cost-matched naive baseline, measured by
restored connectivity under an identical disruption. Against shortest-geometric-
gap closure (I3) it does not win in any of 1,212 pre-registered scenarios at any
of three budgets. H2 is rejected.

**NOT falsified — I1 does beat two of the four baselines.** On the same
pre-registered scenarios at 2000 m, I1 beats random placement 150–18
(Wilcoxon p = 8.5e-15) and highest-degree placement 193–0 (p = 2.0e-33); at
1000 m, 70–38 and 86–2. It is beaten by exactly one baseline, the geometric one.
Saying "the proposer has no advantage" is therefore wrong, and it has been
removed below.

**Replication caveat.** In the separately frozen post-hoc size-relative set
(1,515 records / 1,414 unique scenarios), the direction replicates with smaller
p-values, **but I1 wins 13 scenarios against I3** (2 at 500 m, 8 at 1000 m, 3 at
2000 m). The "never wins" property is specific to the pre-registered set and must
not be quoted as though it replicated.

**Also falsified, by implication:** the framing that made the counterfactual
validation loop look like a contribution. Validating that a proposal helps is
not evidence that the proposal is *good*; it distinguishes a proposal only from
doing nothing, and doing nothing was never the relevant comparison. Worse,
Δ ≥ 0 is guaranteed by construction (see §3), so "it helped" carries no
information at all.

**NOT falsified — important to keep separate:**

* Not falsified: that topological criticality is meaningful. This experiment
  never tested criticality ranking. It tested *post-fragmentation repair*, an
  objective in which node identity provably washes out.
* Not falsified: that the counterfactual validation *protocol* is sound. The
  protocol is what produced this result. It worked exactly as intended — it
  found that the thing it was validating has no advantage.
* Not falsified: any claim about Bengaluru. No Bengaluru graph was used in this
  experiment; all graphs are synthetic families with real geometry.
  **Correction:** the original reason given here — "Overpass unreachable" — was
  false. A real Bengaluru OSM extract is committed at
  `backend/cache/befdaed17dcd4b1967a71e322ded5946f4da89e1.json` and rebuilds
  offline to a connected 13,486-node / 19,117-edge graph with real geometry. P2.2
  did not use it. Running P2.2 on it would be a **NEW EXPERIMENT** and has not
  been run.
* Not falsified: anything about flood prediction. H1 was not run.

---

## 3. What remains scientifically supported

Supported by committed, reproducible evidence, all on synthetic topologies:

1. The counterfactual validation protocol (propose → add to baseline → re-run
   the identical stressor → report measured Δ, including Δ ≤ 0) functions and
   produces falsifiable negative results.
2. The penalty-free decomposition (`unreachable_fraction`,
   `reachable_path_inflation`) is a usable objective; it was the endpoint that
   produced a clean, interpretable verdict where RI could not.
3. ~~No intervention method ever made a network worse~~ — **withdrawn as a
   finding.** `frac_lt_0 = 0.00` in every cell of both sets, but this is a
   THEOREM, not evidence. Adding edges to `G` and then ablating the same node set
   yields a supergraph of the perturbed graph on the same nodes; reachability is
   monotone in edges and `pairs_evaluated` is unchanged, so
   `delta_unreachable_fraction >= 0` always. The observation confirms the
   implementation is self-consistent; it says nothing about the methods. For I5
   it is doubly tautological — the selection rule is `if d > best_d` with
   `best_d` initialised to 0.0.
4. Targeted attack dominates random failure on chokepoint topologies but **not**
   on homogeneous lattices (`tests/test_no_clamps.py`). Retained negative result.
5. RI does not support intervention ranking. Across penalties
   {900, 1800, 3600, 7200, 14400} s, the full 20-candidate ranking was
   **identical in 0 of 8 cases**; top-1 was stable in **3 of 8**; the minimum
   *defined* Spearman rho against the 3600 s reference is **0.390**; and RI's top
   pick disagrees with the penalty-free metric's top pick in **6 of 8**. In 3 of
   40 penalty-cells RI saturated to a single constant, leaving rho undefined
   (reported as `null`, not zero). (F7. Earlier versions of this line read
   "ranking is not invariant ... in 0/7 cases", which both used the wrong
   denominator — there are 8 cases, 0 skipped — and, as written, asserted the
   opposite of the finding. The criterion is strict: one case fails it on 1
   discordant pair out of 190, another on 123.)
6. At the production setting k=5, betweenness top-10 overlap with exact averages
   0.34 across 5 seeds (range [0.10, 0.60]) on the 13,486-node topology proxy.
   At the exact production configuration (k=5, **seed 42**) top-**5** overlap is
   **0.00**. See `POSTMORTEM_A5.md`.

7. An irreducible 30–58% of `unreachable_fraction` can never be repaired by any
   intervention: when a sampled source node is itself ablated, all of its pairs
   are charged as severed. Measured median irreducible share — grid_400 0.575,
   chokepoint_196 0.330, ring_of_cliques_48 0.443, geometric_497 0.296,
   radial_25 0.545. This cancels in paired comparisons, so the I1-vs-I3 verdict
   is unaffected, but every absolute Δ understates the repaired share of
   *repairable* damage by roughly 1.4–2.4×.

8. **No effect size was reported for any comparison.** `cliffs_delta` in
   `07_aggregate.py` is skipped whenever n > 400, which is every cell of both
   sets. The paired median difference is 0.000000 with 95% bootstrap CI
   [0.0, 0.0] and `ci_excludes_zero` is `False` in all 24 comparisons; the small
   p-values come entirely from the 6.5–16% of non-tied pairs. An effect size has
   deliberately **not** been computed after the fact.

---

## 4. Does a defensible next research question exist?

**A hypothesis is suggested by this result. It has NOT been tested and must not
be reported as though it had been.**

The mechanism in §1.5 is specific to *repair*: once a network has fragmented,
the objective depends only on which components are joined, so the identity of
individual nodes is irrelevant. That argument does **not** transfer to
*prevention*, where the decision is which node **not to lose**, and that choice
changes *which fragmentation occurs at all*. The quantity that washes out
post-hoc is the quantity being chosen ex ante.

Candidate question:

> Does topological criticality ranking identify the nodes whose protection most
> reduces expected connectivity loss under a realistic disruption distribution,
> compared with degree, random, and geometric baselines at equal protection
> budget?

Why it is structurally different from what was just falsified: the decision
variable is node identity, the objective is sensitive to node identity, and the
baselines cannot trivially dominate by being cheaper — protection cost per node
is roughly uniform, so the cost lever that decided H2 is absent.

**Three reasons to be sceptical before committing to it:**

1. It is close to standard network-robustness work (targeted immunisation,
   attack tolerance). Novelty would have to come from the evaluation, not the
   algorithm.
2. A5 showed the production ranking recovers 3–4 of the true top 10 at k=5. Any
   preventive study must use exact or high-k betweenness, which also means the
   deployed system would not be the thing validated.
3. The H1 hazard/consequence distinction still applies. A preventive study
   measures *consequence*, so it must not be validated against an observed
   failure list — that was the original category error.

**This is a hypothesis generated by a negative result, not a finding.** It
requires its own pre-registration, its own frozen scenarios, and its own
falsification criteria before any code is written.

---

## 5. Evidence required to test it

| # | Evidence | Why it is required | Available here? |
|---|---|---|---|
| 1 | A real road graph with geometry, committed and fingerprinted | Synthetic families cannot support a claim about cities; the H2 mechanism was graph-independent but a prevention result would not be | **YES — this gate is CLEARED.** `backend/cache/befdaed17dcd4b1967a71e322ded5946f4da89e1.json` is a committed Overpass extract (39,264 nodes / 12,135 ways, bbox 12.907–12.998 N / 77.558–77.650 E) that rebuilds OFFLINE via OSMnx 1.9.3 to a connected 13,486-node / 19,117-edge graph with real coordinates. The earlier "**No** — Overpass blocked" entry was wrong. It still needs fingerprinting before use. |
| 2 | A disruption distribution with an empirical basis | Protection value is an expectation over disruptions; an invented distribution makes the expectation arbitrary. Spatially-correlated removal was a guess | **No** |
| 3 | Pre-registered protection budget and cost model | The H2 failure was a budget effect. Per-node protection cost must be stated before running | Definable now |
| 4 | Baselines: degree, random, geometric (betweenness-free) | Same discipline that killed H2 | Definable now |
| 5 | Exact or high-k betweenness | k=5 rankings are unreliable (A5) | Computable — 504 s at 13.5k nodes |
| 6 | Pre-registered failure criteria with a top-K statistic, not global ρ | The A5 design error must not repeat | Definable now |
| 7 | Power analysis over scenario count | H2's median/CI were uninformative due to 85–94% ties; a prevention study needs a tie-robust design stated up front | Definable now |

**Item 1 is no longer blocking** (see the corrected row above). **Item 2 still
is**, and it cannot be waved through: without a defensible disruption
distribution, "expected connectivity loss" has no referent, and the study would
reproduce H2's weakness of measuring against an assumption rather than the world.

The existence of the real graph is a **CORRECTION TO DOCUMENTATION, not a
result.** Nothing in this repository has been run on it. Re-running A5, A7 or
P2.2 against it would each be a **NEW EXPERIMENT**; none has been performed, and
none should be performed in order to obtain a better-looking number.
