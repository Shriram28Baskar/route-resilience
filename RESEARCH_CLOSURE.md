# Route Resilience — Research Closure

**Status: frozen as a research artifact. Not a CODS Main Track research paper in its
current form.**

This document closes the research line. It does not modify any experimental result
and makes no claim beyond what the committed artifacts support.

> **Revision after an adversarial re-audit.** Thirteen numbers, mechanism claims
> and limitations in the first version of this document did not survive
> independent recomputation from the committed artifacts. Every one is corrected
> below and the correction is stated in place rather than silently applied. No
> experimental artifact was altered to make this document read better; the raw
> JSONL, the frozen scenario files and the pre-registered aggregate are
> bit-identical to what they were. See `experiments/PREREGISTRATION_DEVIATIONS.md`
> D8–D11 and the changelog at the end of this file.

---

## 1. Original hypothesis and why it was rejected

**H2, as pre-registered:**

> Under an identical disruption at matched cost, do counterfactually-validated
> interventions produce larger resilience gains than naive interventions?

**Rejected.** Route Resilience's proposer (`/simulate/ablate/prescribe`, I1) won
**0 of 1,212** pre-registered scenarios against shortest-geometric-gap closure
(I3), at all three budgets (Wilcoxon p = 5.36e-15, 1.72e-29, **1.15e-14**;
median difference 0.000000, 95% bootstrap CI [0.0, 0.0]; 1,131 / 1,043 / 1,133
ties).

Three qualifications the first version of this document omitted:

* **The replication is partial.** The separately-frozen post-hoc size-relative
  set — **1,515 records / 1,414 unique scenarios, 101 exact duplicates** (see
  D8) — gives smaller p-values (down to 4.55e-56 for the I1-vs-I3 comparison at
  1000 m), **but I1 wins 13 scenarios there**: 2 at 500 m, 8 at 1000 m, 3 at
  2000 m. "Never wins" is a property of the pre-registered set only.
* **I1 loses to one baseline, not to all four.** At 2000 m it beats random
  placement 150–18 (p = 8.5e-15) and highest-degree placement 193–0
  (p = 2.0e-33); at 1000 m, 70–38 and 86–2. The earlier claim that "the proposer
  has no advantage" is withdrawn.
* **No effect size is reported.** `cliffs_delta` is skipped at n>400, which is
  every cell. `ci_excludes_zero` is `False` in all 24 comparisons — the median
  scenario shows no difference — and the p-values come entirely from the 6.5–16%
  of non-tied pairs. One has deliberately not been computed after the fact.

**Mechanism — TWO mechanisms, not one.** Both methods bridge a real partition
100% of the time and their endpoint degrees have the same median (4.0, though not
the same distribution).

1. **Cost.** I1's edges are 2.6× longer (median 1454.8 m vs 556.7 m), because
   `ablate_prescribe` selects `max(component, key=degree)` with no reference to
   geometry. Under a length budget it is priced out of 245 / 165 / 31 of the 253
   partitioned scenarios at 500 / 1000 / 2000 m.
2. **Target component.** `ablate_prescribe` joins `comps_sorted[i]` to
   `comps_sorted[i+1]` — a **chain**. `propose_nearest_gap` joins `comps[0]` to
   `comps[i+1]` — a **star** centred on the giant component. Over the 120-scenario
   replay, **24.1% of I1's edges never touch the giant component; 100% of I3's
   do.** Since `apply_budget` skips an unaffordable proposal and continues, I1 can
   buy only its 2nd or 3rd edge and merge two *minor* fragments. This mechanism was
   missed in the first version of this document, which attributed everything to cost.

Restricted to scenarios where both methods acted, I1 won 0 of 318. When both added
the same number of edges the result was a tie in 174 of 179 cases (97%). **Of I3's
48 wins at 2000 m, 43 (89.6%) involved buying more edges and 5 did not** — the
earlier "43/43" was wrong and contradicted the post-mortem's own table; the 5
exceptions are mechanism 2.

The tie rate follows from the objective's definition: joining components A and B
restores exactly the OD pairs straddling A and B, a set independent of *which node*
of A is wired to *which node* of B. **Conditional on the component pair, endpoint
selection is worth nothing; edge cost is worth a great deal.** The qualifier
matters — *which components* are joined is a separate lever, it is not invariant,
and I1 gets it wrong too. The unqualified claim that endpoint choice is universally
irrelevant is withdrawn.

**H1 (hazard prediction) was never run.** It required flood ground truth that was
not collected, and the design work established that validating a *consequence*
ranking against an observed *failure* list is a category error unless hazard and
consequence are separated.

---

## 2. Engineering contributions that remain valuable

These are real and independent of any publication outcome.

**P0 — removed four result-altering devices.**
- Random-failure RI was raised to `betweenness + 0.05` whenever random was more
  damaging. Measured firing on a 20×20 grid: true random RI 0.4317 → reported 0.8355.
- Counterfactual validation floored at `attacked_ri + 0.025`, so it could never
  report a failed intervention.
- Cascade truncated to 65% of the previous iteration, plus a 98% threshold cap
  commented "so we always show some data."
- `/simulate/route` ablated an extra node **on the computed path** whenever the
  caller's ablation didn't change the route. Re-measured at commit `83e6b5e` on
  the same 40-case chokepoint sweep (seed 7) that the regression test uses:
  **27/40 = 68%** of single-node scenarios got a fabricated failure and
  **8/40 = 20%** raised an unhandled `TypeError` (HTTP 500) on the severed-pair
  case — the exact case the tool exists to model. Post-fix: 0/40 and 0/40.
  *(The first version of this document said 60% and 25%. Neither reproduced.)*

**P0 — RI made explicit.** `penalty_s` parameterised and echoed with `ri_floor` and
`ri_is_cross_network_comparable: false`. Added the penalty-free decomposition
(`unreachable_fraction`, `reachable_path_inflation`). No normalised scalar was
invented: weighting "longer" against "impossible" has no principled basis here.
Two properties of the decomposition, added after the audit and documented in
`app/simulation/resilience.py`: `Δ unreachable_fraction ≥ 0` is a **theorem**
under edge addition, and **30–58% of `unreachable_fraction` is irreducible**
because a sampled source that is itself ablated has all of its pairs charged as
severed. `reachable_path_inflation` is a **ratio of means**, not a mean of ratios;
the docstring previously said the latter.

**P0 — ML quarantine.** `/graph/heal` wrote the global analysis graph, so uploading
any tile on `/explain` silently replaced the network every other endpoint analysed.
Now isolated; the resilience engine imports with torch, torchvision, rasterio,
scikit-image, transformers, timm, albumentations, cv2 and shap all absent.

**P1 — data provenance.** Every numeric endpoint declares
`measured / derived / synthetic / unavailable` with its inputs and assumptions. Six
endpoints that previously returned confident numbers from constants now return
**503** naming the missing artifact. Dead OD-matrix code removed (four identifiers
that each appeared exactly once, at their definition, while the docstring claimed an
OD model). The DEM fallback that assigned every node 900.0 m — turning the flood
model into a global on/off switch — now raises.

**P1 — reproducibility.** Deterministic graph fingerprint (node IDs, edge set,
routing weights, AOI). The centrality cache was previously keyed only on a boolean
flag and returned **13,486 scores for a 25-node graph with zero node overlap**; it is
now refused or recomputed, and raises under `STRICT_GRAPH_CACHE=true`.

**P1 — build hygiene.** `npx next build` fixed (one TS error masked a live bug:
code read `CascadeStep.ablated_nodes` where the field is `ablated`). Docker fixed:
`output: "standalone"`, `public/`, lockfile + `npm ci`, `NEXT_PUBLIC_API_BASE` moved
to a build arg. Requirements split into core / raster / ml.

**P1 — tests.** 2 → **53 passing + 1 documented xfail** (51 + 1 at P1; the post-audit
rewrite of the withdrawn invariance test added two), chosen to protect scientific
claims rather than coverage.

**P1 — a second clamp sweep found three more.** `max(rgs, 0.05)` and
`max(rgs, 0.08)` (commented "ensure positive for demo") in `recommendations.py`, and
`max(ri_base, ri_proj + rec["rgs"])` in `/simulate/simulate-investment`, which also
used an unseeded `random.choice`. The bypass gain additionally compared two RIs
computed against *different* baselines, so its difference was not a gain at all.

---

## 3. Strongest experimentally established negative findings

All reproducible from committed artifacts under recorded seeds. **All on synthetic
graphs or a weightless topology proxy; no experiment was run on a real road
network** (one is nonetheless available offline — see §9.4).

1. **Intervention placement (H2).** 0 wins in 1,212 pre-registered scenarios against
   shortest-gap closure; 0 of 318 head-to-head where both acted. In the post-hoc
   relative set I1 wins **13** — the result does not fully replicate.
2. **Objective degeneracy.** 97% tie rate (174/179) when edge counts match. **43 of
   I3's 48 wins (89.6%)** came from buying more edges; the other 5 came from joining
   the giant component while I1 joined two minor fragments. *(Was "43/43", which
   contradicted the post-mortem's own table.)*
3. **k=5 betweenness is unusable for a top-K display.** On the 13,486-node topology
   proxy, seed-averaged Spearman ρ = 0.957 at k=5 while **top-10 overlap with exact
   is 0.34**, range [0.10, 0.60] across seeds. **ρ is non-monotonic in k: 0.957 at
   k=5, peaking at 0.983 at k=25, and back down to 0.971 at k=1000**, while top-10
   overlap climbs 0.34 → 0.94. At the exact production configuration (k=5, seed 42)
   **top-5 overlap is 0.00** — none of the five most critical junctions is recovered.
   *(The earlier "ρ is near-flat across k (0.957→0.983) while top-10 overlap moves
   0.34→0.94" paired a k=5→k=25 range against a k=5→k=1000 range. The corrected
   statement is strictly stronger: ρ DECLINES over the interval in which top-K
   agreement more than doubles.)*
4. **RI does not rank interventions.** Over penalties {900, 1800, 3600, 7200,
   14400} s the full 20-candidate ranking was identical in **0 of 8** cases (8
   evaluated, 0 skipped); top-1 stable in **3 of 8**; minimum *defined* ρ against the
   3600 s reference **0.390**; RI's top pick disagrees with the penalty-free metric's
   top pick in **6 of 8**. In 3 of 40 penalty-cells RI saturated to a single constant
   and ρ is undefined (emitted as `null`, not 0).
   *(Was "Ranking not invariant across finite penalties in 0 of 7 cases; top-1 stable
   in only 4/7; ρ … falls to 0.565." The denominator, the top-1 count and the minimum
   ρ were all wrong, and the sentence as written asserted the opposite of the
   finding. The criterion is also strict: one case fails it on 1 discordant pair out
   of 190, another on 123.)*
   This **withdraws the README/CLAIMS claim** that invariance held. The reason
   previously given for the withdrawal — "that earlier test used 5 coarse candidates
   where ties were unlikely" — was also wrong: the earlier test did not rank
   interventions at all, it ranked five **ablation scenarios**. It is now
   `test_ablation_severity_ranking_is_stable_across_finite_penalties`, and
   `test_intervention_ranking_is_not_invariant_across_finite_penalties` pins the
   refutation.
5. **Targeted attack does not universally dominate random failure.** It dominates on
   chokepoint topologies and loses on homogeneous lattices. Retained; it is the result
   the removed clamp existed to suppress.
6. ~~**No method ever made a network worse.**~~ **Withdrawn as a finding.**
   `frac_lt_0 = 0.00` in every cell of both sets, but adding edges to `G` and then
   ablating the same node set yields a supergraph of the perturbed graph on the same
   nodes; reachability is monotone in edges and `pairs_evaluated` is unchanged, so
   `Δ unreachable_fraction ≥ 0` **always**. It is a theorem about the construction,
   not evidence about the methods. For I5 it is doubly tautological (`if d > best_d`
   with `best_d` initialised to 0.0).
7. **The I5 "oracle" is neither an oracle nor an upper bound.** It evaluates the best
   **single** edge from a bounded 15-candidate pool drawn from the two largest
   components, while every other method may buy several edges within the same budget.
   I3 beats it in **55 / 78 / 79** of 1,212 scenarios at 500 / 1000 / 2000 m; I1 beats
   it 17–9 at 2000 m (p = 0.62); I2-random beats it 19 times. "Headroom" and "upper
   bound" are withdrawn.
8. **An irreducible 30–58% of `unreachable_fraction` can never be repaired** —
   grid_400 0.575, chokepoint_196 0.330, ring_of_cliques_48 0.443, geometric_497
   0.296, radial_25 0.545 — because a sampled source that is itself ablated has all
   of its pairs charged as severed. Cancels in paired comparisons, so the I1-vs-I3
   verdict is unaffected; dilutes every absolute Δ by roughly 1.4–2.4×.

---

## 4. Literature findings that rule out novelty

| Finding | Status | Primary source |
|---|---|---|
| **C3** global ρ overstates top-K agreement | **Already established** | Geisberger, Sanders & Schultes (ALENEX 2008) state it verbatim on road networks: *"The Euclidean distance is mostly governed by the nodes with large betweenness, whereas the number of inversions treats all nodes equally"*, with level-stratified head analysis. Brandes & Pich (2007) already report value/rank divergence. Riondato & Kornaropoulos (WSDM 2014; DMKD 2016) give a dedicated top-k variant with guarantees. Matta, Ercal & Sinha (Comput. Soc. Netw. 2019) motivate their benchmark by *"only the top or top k vertices… are required."* |
| **C3** general claim (ρ/τ unfit for top-weighted lists) | **Already established** | Webber, Moffat & Zobel (ACM TOIS 2010), RBO — the paper exists precisely because τ/ρ are *"unweighted, placing as much emphasis on disorder at the bottom of the ranking as it does on disorder at the top."* |
| **C3** in network science specifically | **Already applied** | Rajeh, Savonnet, Leclercq & Cherifi (Complex Networks IX, 2020) already use **RBO and Jaccard** alongside Spearman to compare centrality rankings. |
| **C1** endpoint degeneracy | **Known** | *Sci. Rep.* (2026) rewiring paper, verbatim: *"any node from the disconnected component to the LCC will result in the same number of edges and nodes in the newly connected component."* Phys. Rev. E 92:052806 (2015) already benchmarks shortest-new-link repair against random. |
| **C4** penalty for unreachable OD pairs | **Standard practice, and our own metric** | Fixed large-penalty treatment of unreachable pairs, and separating reachability from penalized path length, are established in road/transit criticality work. The index itself is used by nobody else. |

**Conclusion: none of the three findings is novel.** Additional real networks would
replicate a 2008 result, not extend it.

---

## 5. Claims the repository can safely make

- The system removes four (later seven) result-altering devices that previously
  overwrote measured values, with before/after measurements for each.
- Every numeric endpoint declares provenance; endpoints lacking required data return
  503 rather than a substitute value.
- Centrality results are keyed to a deterministic graph fingerprint; a mismatched
  cache is refused.
- The resilience engine runs without any ML or raster dependency.
- 53 tests + 1 documented xfail pass in both cache modes; clean-clone build verified.
- **Under a connectivity-restoration objective on the tested synthetic topologies,**
  the system's intervention proposer does not outperform shortest-gap closure — while
  it does outperform random and highest-degree placement.
- **At k=5 on the 13,486-node topology proxy,** seed-averaged top-10 betweenness
  overlap with exact is 0.34 (top-5 overlap 0.00 at the production seed) — a
  re-demonstration of a known phenomenon, not a new one.
- **A real Bengaluru road graph is reproducible offline from a committed artifact**
  (13,486 nodes / 19,117 edges). This is a fact about the repository's contents, not
  a research result, and **no experiment here used it.**

Every empirical claim must carry: *synthetic graphs or a weightless topology proxy
only; no experiment was run on a real road network; no Bengaluru measurement.*

---

## 6. Claims that must not be made

Already removed in P1 and to stay removed: IoU 0.73, F1 0.81, "+12% occlusion
retention", Precision@5 = 4/5, Precision@10 = 8/10, "13,486 intersections",
"16,000+ road segments", "44,552 residents impacted", "24 emergency facilities",
"312 vulnerable intersections", "answers that in 3 seconds", the "(Confidence: 78%)"
cascade extrapolation, fabricated infrastructure labels, and the ₹/$ cost estimates.

Additionally prohibited from here on:

- **Any Bengaluru measurement.** No experiment was run on a real road graph. The
  13,486-node object used in A5 is a topology proxy with uniform placeholder weights
  and no coordinates. *(Correction: the reason given here was "Overpass was
  unreachable". That was false — see §9. The prohibition stands; its justification
  changes from "unavailable" to "was not used".)*
- **"Intervention rankings are invariant across finite RI penalties."** Withdrawn —
  contradicted by A7 (identical in **0 of 8** cases).
- **"No intervention method ever made a network worse."** Withdrawn — a theorem, not
  a finding.
- **"Every case I3 wins is one where it bought more edges (43/43)."** Withdrawn —
  43 of 48.
- **"Endpoint selection is worth nothing."** Withdrawn unless qualified by
  *conditional on the component pair joined*.
- **"I5 is an upper bound / establishes headroom."** Withdrawn — it is the best single
  edge from a bounded 15-candidate pool and loses to I3 in 6.5% of scenarios.
- **"The proposer has no advantage."** Withdrawn — it beats two of four baselines.
- **Any effect size** for the intervention comparisons. None was computed, and none
  may be computed now that the outcome is known.
- **"Pre-registered" as though a protocol document existed.** It does not. The word
  means "frozen and committed before the run" (git: `2ffc871` → `5f3b9f2`).
- **Any novelty claim for C1, C3 or C4.** See §4.
- **Any validation claim.** H1 was never run; no ground truth exists.
- **"Counterfactually validated interventions improve resilience"** as a capability
  statement. The validation protocol works; what it measured is that the proposer has
  no advantage.
- **Evacuation, change detection, autonomous/citizen/VLM functionality.** Not
  implemented; `/simulate/evacuate` returns 503.

---

## 7. Final status

**Not a CODS Main Track research paper in its current form.**

The archival criterion is explicit novelty. All three candidate findings are known;
the evidence is a single self-authored system on synthetic graphs; there is no real
network and no ground truth. Combining known findings does not create novelty, and
any unifying framework would be constructed after the fact.

Venue facts (primary sources): CODS 2026 has merged Research and Applied Data Science
into a single **Main Track** judged on *"novelty of the described approaches as well
as suitability for real-world applications."* Negative results have precedent in
**short papers**, per the CODS-COMAD 2024 CFP, not the main archival track.
Reproducibility *"will play an important role in the assessment"* but is not a
contribution category. The CODS 2026 Main Track deadline (13 → 20 August 2026) has
passed.

The defensible outcome is that the work's value was **engineering**, and it has been
collected: live defects found and removed, and a reproducible harness left behind.

---

## 8. Artifact inventory

### Commits, in order

| # | Content |
|---|---|
| 1 | P0 — clamps removed, route crash fixed, RI explicit, ML quarantined |
| 2 | P1 — provenance, fingerprinting, build hygiene, core tests |
| 3 | P1 completion — UI provenance, surviving RGS clamps, claim audit |
| 4 | P2.0/P2.2 partial — scripts, frozen scenarios, A5 synth, A7 |
| 5 | ignore raw outputs while in flight |
| 6 | P2.0 complete — A5 on the 13,486-node proxy |
| 7 | P2.2 — raw intervention outputs + pre-registered aggregate |
| 8 | P2.2 — post-hoc relative-k aggregate (separate, never merged) |
| 9 | Post-mortem — H2 mechanism + A5 ρ/top-K trap |
| 10 | Research closure (this document) |
| 11 | Post-audit corrections: 13 numerical/mechanism/limitation fixes, deterministic scenario seeding, relative-set deduplication, A7 JSON validity, stale test replaced |

Artifact hashes below are the durable identifiers; they are independent of
commit SHAs and verify with `sha256sum`.

### Experimental artifacts (SHA-256, first 16 hex)

| Artifact | Hash | Size |
|---|---|---|
| `scenarios/scenarios.json` (1,212, pre-registered) | `b39ce17b95c6ec43` | 370 KB |
| `scenarios/scenarios_relative.json` (1,414, post-hoc) | `e896c598f3647b30` | 736 KB |
| `results/a5_k_sensitivity_proxy.json` | `d2ff66ba1e28dd10` | 13 KB |
| `results/a5_k_sensitivity_synth.json` | `911c0736c112659a` | 27 KB |
| `results/a7_ri_penalty.json` | **`d3e4daeb1f4f2201`** | 24 KB |
| `results/a7_ri_penalty.PRE_AUDIT_nan.json` | `1f640ea12ebc2590` | 24 KB — preserved original; **deliberately not valid strict JSON** (3 bare `NaN`) |
| `results/interventions_raw.jsonl` (19,392 rec) | `05c4bd4e6ffa6fdc` | 10.5 MB |
| `results/interventions_raw_relative.jsonl` (24,240 rec) | `47c49de0445720b3` | 13.2 MB |
| `results/interventions_aggregate_absolute.json` | **`7c98f45494a3c8ff`** (was `548415c6c7a0d6b4`) | 23 KB |
| `results/interventions_aggregate_relative.json` | **`53131a72f52e8882`** (was `5cf42bbe2d2921dd`) | 23 KB |
| `results/postmortem_i1_vs_i3.json` | `bfe501923d310c31` | 85 KB |

> **Aggregate hashes changed; the numbers behind them did not (absolute set).** Both
> aggregates were regenerated after the deduplication fix. For the **pre-registered
> absolute set every one of the 60 table cells, all 12 paired comparisons and the
> stratification are bit-identical** to the pre-audit file (`548415c6c7a0d6b4`); only
> added metadata fields differ. For the **relative set**, 15 of 60 `all_scenarios`
> cells and 20 of 40 stratified entries changed because 101 duplicated all-zero
> `radial_25` scenarios were removed — see the changelog. The pre-audit aggregates
> are recoverable from git history; the raw JSONL they were computed from is
> unchanged.
>
> **`a7_ri_penalty.json` was regenerated** to emit `null` instead of bare `NaN`
> (which is not valid JSON). Every other value is identical; verified field by
> field. The original is preserved as `a7_ri_penalty.PRE_AUDIT_nan.json`.
>
> The scenario files also carry an internal `sha256_of_body` (`c222fbd2e9b56390`,
> `2e8dd6747a4f8ded`) computed over the payload *excluding* that field; the runner
> verifies it before executing. Both differ from the whole-file hashes above by
> construction. Both verify.

### Reproducibility assets

`experiments/04_gen_scenarios.py`, `05_run_interventions.py`,
`06_ablation_a5_k_sensitivity.py`, `06_ablation_a7_ri_penalty.py`, `07_aggregate.py`,
`08_postmortem_i1_vs_i3.py` · `PREREGISTRATION_DEVIATIONS.md` (D1–D7, including two
self-reported design errors) · `POSTMORTEM_H2.md` · `POSTMORTEM_A5.md` ·
`CLAIMS.md` · `backend/data/README.md` · `backend/tests/` (53 + 1 xfail) ·
bootstrap 10,000 reps seeded (`20260915`), `STRICT_GRAPH_CACHE` mode.

**Reproducibility caveat — the frozen scenario sets cannot be regenerated.** They
were built with `MASTER_SEED + hash((label, family, k, replicate)) % 10_000_019`.
CPython salts `hash()` over str-containing tuples per process and `PYTHONHASHSEED`
was never pinned, so three successive runs produced three different seeds. Only the
12 deterministic S5_targeted scenarios (1.0% of 1,212) were regenerable. The
generator now uses `hashlib.sha256` and is verified identical across separate
processes, but it **cannot reproduce the committed files**, which are retained
untouched as evidence and refuse to be overwritten without `--overwrite-frozen`.
What the committed `sha256_of_body` guarantees is that the runner executed exactly
the scenarios on disk — not that those scenarios can be derived from the code.

---

## 9. Possible future directions

**All UNVALIDATED. None implemented, none tested, none endorsed.** Listed only so the
reasoning is not lost.

1. **Objective-matched criticality.** For a connectivity objective, block-cut-tree
   measures (articulation points, OD-pairs-disconnected-on-removal) are the
   theoretically matched quantity; betweenness measures shortest-path flow. *Untested,
   and it would test our own system's measure choice, not a general claim.*
2. **Preventive node protection.** **G1 (a real road graph) is CLEARED** — see
   item 4. **G2 (an empirically-grounded disruption distribution) still blocks it**,
   and cannot be waved through: without one, "expected connectivity loss" has no
   referent. Separately assessed as a replication of Holme et al. (2002) and
   Jenelius et al. (2006).
3. **Exact cached betweenness in production.** Exact costs 504 s at 13,486 nodes and
   centrality is already precomputed and disk-cached, so the k=5 "timeout" rationale
   does not hold. *An engineering change, not research; deliberately not made while an
   evaluation of the current configuration is on record.*
4. **A real graph — ALREADY AVAILABLE. This item was wrong.**
   `backend/cache/befdaed17dcd4b1967a71e322ded5946f4da89e1.json` is a git-tracked
   Overpass 0.7.62.11 response (39,264 nodes / 12,135 ways, bbox 12.90665–12.99830 N
   / 77.55759–77.65045 E, `timestamp_osm_base` 2026-06-16), present since the initial
   commit `f015407`. OSMnx 1.9.3 reads `./cache` by default, so
   `scripts/download_data.py` builds a **connected 13,486-node / 19,117-edge**
   Bengaluru graph with real coordinates **offline** — verified with network sockets
   disabled. The claim that this was "unobtainable", repeated across README.md,
   CLAIMS.md, `PREREGISTRATION_DEVIATIONS.md` D2 and `POSTMORTEM_H2.md`, was **false
   and unverified**: the OSMnx cache directory was never checked.

   What follows and what does not:
   * **Follows:** the "no real network" limitation is withdrawn; gate G1 is cleared;
     the withdrawn README figures "13,486 intersections / 16,000+ road segments" are
     reproducible and have been reinstated; the weightless topology proxy used in A5
     was never necessary.
   * **Does not follow:** any result about Bengaluru. **A5, A7 and P2.2 did not use
     this graph.** Re-running any of them on it is a **NEW EXPERIMENT**; none has
     been run, and none will be run merely to obtain a better-looking number. The
     graph still needs fingerprinting before any result is reported against it.
5. **Technical report rather than a paper.** Positioning the work as a worked example
   of known evaluation pitfalls, citing Geisberger et al. and Webber et al. as prior
   art, with no novelty claim.

---

**Route Resilience is frozen as a research artifact.** Experimental results are not
to be modified, re-run, or reframed.


---

## 10. Post-audit changelog

An adversarial re-audit recomputed all 47 quantitative results from the committed
artifacts. 26 verified exactly, 8 needed qualification, 13 were wrong. This section
records what changed and — equally important — what did not.

### Documentation corrected (no experimental data touched)

| Was | Is | Where |
|---|---|---|
| I3 wins all came from extra edges, 43/43 | **43 of 48 (89.6%)** | §1, §3.2, POSTMORTEM_H2 §1.5 |
| A7: 0 of **7** cases | **0 of 8** (8 evaluated, 0 skipped) | §3.4, POSTMORTEM_H2 §3 |
| A7: top-1 stable in **4/7** | **3 of 8** | §3.4 |
| A7: min ρ **0.565** | **0.390** | §3.4 |
| "ranking **not** invariant in 0 of 7 cases" | rewritten — the sentence asserted the opposite of the finding | §3.4 |
| Pre-fix route sweep **60% / 25%** | **68% (27/40) / 20% (8/40)** | §2 |
| "ρ near-flat across k (0.957→0.983)" | 0.957 at k=5 → **0.971** at k=1000, peak 0.983 at **k=25**, non-monotonic | §3.3, POSTMORTEM_A5 |
| Wilcoxon "p ≤ 1.1e-14" | **p ≤ 1.15e-14** | §1 |
| relative set "1,414 scenarios", elsewhere "1515" | **1,515 records / 1,414 unique / 101 duplicates** | §1, D8 |
| relative set "reproduced this more strongly" | smaller p-values, **but I1 wins 13** | §1 |
| "the proposer has no advantage" | beats I2-random and I4-degree; loses only to I3 | §1 |
| "the only material difference is edge length" | **two** mechanisms — cost **and** chain-vs-star targeting | §1, POSTMORTEM_H2 §1.6 |
| I5 "upper bound / headroom" | **best single edge from a bounded 15-candidate pool**; I3 beats it 55/78/79 | §3.7 |
| "no method made a network worse" as a finding | **theorem**, withdrawn as evidence | §3.6 |
| "OSM extract not committed / unobtainable" | **false** — real graph rebuilds offline | §9.4, README, CLAIMS, D2/D9 |
| "13,486 intersections" UNSUPPORTED | **reinstated as measured** | README, CLAIMS |
| README "31 paths" | **32** | README |
| README "7 endpoints return 503 in a fresh clone" | 5 return **404**; 503 needs a graph loaded | README |

### Code corrected

* `experiments/04_gen_scenarios.py` — `hash()` → `hashlib.sha256` seeding, verified
  identical across separate processes; duplicate k values deduplicated; refuses to
  overwrite the frozen sets without `--overwrite-frozen`.
* `experiments/07_aggregate.py` — drops exact duplicate rows (aborting if any
  duplicate pair disagrees), reports `record_counts`, and states that no effect size
  is computed.
* `experiments/06_ablation_a7_ri_penalty.py` — emits `null` instead of bare `NaN`
  and records `spearman_undefined_penalties` (RI saturation).
* `experiments/05_run_interventions.py` — I5 terminology, the chain-vs-star
  asymmetry, and the 50-vs-30 kph new-edge speed asymmetry documented.
* `backend/app/simulation/resilience.py` — the Δ ≥ 0 theorem, the irreducible
  ablated-source component, and the ratio-of-means definition documented.
* `backend/tests/test_resilience_index.py` — the stale test renamed to
  `test_ablation_severity_ranking_is_stable_across_finite_penalties`; a new
  `test_intervention_ranking_is_not_invariant_across_finite_penalties` pins the
  refutation so the withdrawn claim cannot be silently reinstated.

### Artifacts regenerated

| Artifact | Why | What changed |
|---|---|---|
| `a7_ri_penalty.json` | 3 bare `NaN` made it invalid JSON | `NaN` → `null` only; every other value verified identical field by field. Original kept as `a7_ri_penalty.PRE_AUDIT_nan.json`. |
| `interventions_aggregate_absolute.json` | regenerated by the dedup fix | **Zero numerical change.** All 60 cells, 12 paired comparisons and 40 stratified entries bit-identical; only metadata added. |
| `interventions_aggregate_relative.json` | 101 duplicate scenarios removed | n 1,515 → 1,414 in every cell. **All 12 paired comparisons identical** (they already deduplicated). 15 of 60 `all_scenarios` cells changed; 0 of 60 `partitioned_only`; 20 of 40 stratified. All medians stayed 0.0 except two `S5_targeted\|2000m` cells where n went 15 → 14 (I1 0.0 → 0.0051245, I3 0.0 → 0.0851065 — ordering unchanged). Means and proposal rates rose slightly for **every** method, because the removed duplicates were all-zero `radial_25` rows. No ranking changed. |

### Deliberately NOT changed

* `scenarios/scenarios.json`, `scenarios/scenarios_relative.json` — frozen evidence,
  byte-identical (`b39ce17b95c6ec43`, `e896c598f3647b30`).
* `interventions_raw.jsonl`, `interventions_raw_relative.jsonl` — 19,392 and 24,240
  raw records, byte-identical (`05c4bd4e6ffa6fdc`, `47c49de0445720b3`). The duplicate
  rows are still there; deduplication happens at aggregation.
* `a5_k_sensitivity_proxy.json`, `a5_k_sensitivity_synth.json`,
  `postmortem_i1_vs_i3.json` — byte-identical.
* **No experiment re-run to obtain a different answer.** A7 was re-run only for JSON
  validity and reproduced byte-for-byte apart from the NaN fix. Nothing was run on
  the Bengaluru graph.
* The pre-registered analysis was not altered: D10 (121 duplicate ablation
  signatures, violating the independence assumption) is **disclosed, not corrected**,
  because correcting it after seeing results would be a post-hoc change.

### Still open — see the status section in this repository's audit trail

* **G2** — no empirically-grounded disruption distribution. Blocks any preventive
  study.
* **No pre-registration document.** F1–F6 do not exist; F7/F8 live only in script
  docstrings.
* **No effect size** for any intervention comparison, and none may now be added.
* **Independence violated** in the pre-registered set (D10).
* **The frozen scenario sets remain non-regenerable** (fixed going forward only).
* The §4 literature quotations are external and were **not** re-verified by the audit.
