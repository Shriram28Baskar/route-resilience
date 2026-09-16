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
median degree. **The only material difference is that I1's edges are ~2.6×
longer.**

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
179 cases (97%). Every case I3 wins is a case where it bought more edges (43/43).**

This is not an empirical accident; it follows from the definition of the
objective. `unreachable_fraction` counts origin–destination pairs that were
reachable in the baseline and are not reachable after the disruption. Joining
components A and B restores **exactly the pairs that straddle A and B**, and
that set is identical regardless of which node of A is wired to which node of B.
Any bridging edge, anywhere, restores the same OD pairs.

Therefore, under Δ unreachable_fraction:

* **endpoint selection is worth nothing** — it is the quantity I1 optimises;
* **edge cost is worth everything** — it determines how many component-pairs fit
  inside the budget, and that is the only lever on the objective.

I1 spends its entire modelling effort on the dimension the objective cannot see,
and ignores the only dimension it can.

---

## 2. What the experiment falsified

**Falsified:** that Route Resilience's prescriptive layer produces better
interventions than a cost-matched naive baseline, measured by restored
connectivity under an identical disruption. It does not, in any of 1,212
pre-registered scenarios at any of three budgets. H2 is rejected.

**Also falsified, by implication:** the framing that made the counterfactual
validation loop look like a contribution. Validating that a proposal helps is
not evidence that the proposal is *good*; it distinguishes a proposal only from
doing nothing, and doing nothing was never the relevant comparison.

**NOT falsified — important to keep separate:**

* Not falsified: that topological criticality is meaningful. This experiment
  never tested criticality ranking. It tested *post-fragmentation repair*, an
  objective in which node identity provably washes out.
* Not falsified: that the counterfactual validation *protocol* is sound. The
  protocol is what produced this result. It worked exactly as intended — it
  found that the thing it was validating has no advantage.
* Not falsified: any claim about Bengaluru. No Bengaluru graph was used
  (Overpass unreachable); all graphs are synthetic families with real geometry.
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
3. No intervention method ever made a network worse: `frac_lt_0 = 0.00` in
   every cell of both scenario sets.
4. Targeted attack dominates random failure on chokepoint topologies but **not**
   on homogeneous lattices (`tests/test_no_clamps.py`). Retained negative result.
5. RI cannot support intervention ranking: ranking is not invariant across
   finite penalties in 0/7 cases (F7).
6. At the production setting k=5, betweenness top-10 overlap with exact is 0.34
   on a 13,486-node graph (see `POSTMORTEM_A5.md`).

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
| 1 | A real road graph with geometry, committed and fingerprinted | Synthetic families cannot support a claim about cities; the H2 mechanism was graph-independent but a prevention result would not be | **No** — Overpass blocked |
| 2 | A disruption distribution with an empirical basis | Protection value is an expectation over disruptions; an invented distribution makes the expectation arbitrary. Spatially-correlated removal was a guess | **No** |
| 3 | Pre-registered protection budget and cost model | The H2 failure was a budget effect. Per-node protection cost must be stated before running | Definable now |
| 4 | Baselines: degree, random, geometric (betweenness-free) | Same discipline that killed H2 | Definable now |
| 5 | Exact or high-k betweenness | k=5 rankings are unreliable (A5) | Computable — 504 s at 13.5k nodes |
| 6 | Pre-registered failure criteria with a top-K statistic, not global ρ | The A5 design error must not repeat | Definable now |
| 7 | Power analysis over scenario count | H2's median/CI were uninformative due to 85–94% ties; a prevention study needs a tie-robust design stated up front | Definable now |

Items 1 and 2 are blocking and neither is obtainable in this environment.
Item 2 in particular cannot be waved through: without a defensible disruption
distribution, "expected connectivity loss" has no referent, and the study would
reproduce H2's weakness of measuring against an assumption rather than the world.
