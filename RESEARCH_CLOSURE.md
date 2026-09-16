# Route Resilience — Research Closure

**Status: frozen as a research artifact. Not a CODS Main Track research paper in its
current form.**

This document closes the research line. It does not modify any experimental result
and makes no claim beyond what the committed artifacts support.

---

## 1. Original hypothesis and why it was rejected

**H2, as pre-registered:**

> Under an identical disruption at matched cost, do counterfactually-validated
> interventions produce larger resilience gains than naive interventions?

**Rejected.** Route Resilience's proposer (`/simulate/ablate/prescribe`, I1) was
beaten by shortest-geometric-gap closure (I3) in **0 of 1,212** pre-registered
scenarios at all three budgets (Wilcoxon p ≤ 1.1e-14). A separately-frozen post-hoc
set of 1,414 scenarios reproduced this more strongly (p down to 4.5e-56).

**Mechanism, established in the post-mortem.** Both methods bridge a real partition
100% of the time and select endpoints of identical median degree (4.0). The only
material difference is cost: I1's edges are 2.6× longer (median 1455 m vs 557 m),
because `ablate_prescribe` selects `max(component, key=degree)` with no reference to
geometry. Under a length budget that is fatal — but not the whole story. Restricted
to scenarios where both methods acted, I1 still won 0 of 318; when both added the
same number of edges the result was a tie in 174 of 179 cases (97%), and every case
I3 won was one where it bought more edges (43/43).

This follows from the objective's definition. Joining components A and B restores
exactly the OD pairs straddling A and B, a set independent of which node of A is
wired to which node of B. **Under `Δ unreachable_fraction`, endpoint selection is
worth nothing and edge cost is worth everything.** The system spent its entire
modelling effort on a dimension the objective cannot see.

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
  caller's ablation didn't change the route: 60% of single-node scenarios got a
  fabricated failure, and 25% raised an unhandled `TypeError` (HTTP 500) on the
  severed-pair case — the exact case the tool exists to model. Post-fix: 0/40 and 0/40.

**P0 — RI made explicit.** `penalty_s` parameterised and echoed with `ri_floor` and
`ri_is_cross_network_comparable: false`. Added the penalty-free decomposition
(`unreachable_fraction`, `reachable_path_inflation`). No normalised scalar was
invented: weighting "longer" against "impossible" has no principled basis here.

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

**P1 — tests.** 2 → **51 passing + 1 documented xfail**, chosen to protect scientific
claims rather than coverage.

**P1 — a second clamp sweep found three more.** `max(rgs, 0.05)` and
`max(rgs, 0.08)` (commented "ensure positive for demo") in `recommendations.py`, and
`max(ri_base, ri_proj + rec["rgs"])` in `/simulate/simulate-investment`, which also
used an unseeded `random.choice`. The bypass gain additionally compared two RIs
computed against *different* baselines, so its difference was not a gain at all.

---

## 3. Strongest experimentally established negative findings

All reproducible from committed artifacts under recorded seeds. **All on synthetic
graphs; no real road network was used.**

1. **Intervention placement (H2).** 0 wins in 1,212 pre-registered scenarios against
   shortest-gap closure; 0 of 318 head-to-head where both acted.
2. **Objective degeneracy.** 97% tie rate when edge counts match; 43/43 of I3's wins
   came from buying more edges.
3. **k=5 betweenness is unusable for a top-K display.** On a 13,486-node graph,
   Spearman ρ = 0.957 while **top-10 overlap with exact is 0.34**, range [0.10, 0.60]
   across seeds. ρ is near-flat across k (0.957→0.983) while top-10 overlap moves
   0.34→0.94.
4. **RI cannot rank interventions.** Ranking not invariant across finite penalties in
   **0 of 7** cases; top-1 stable in only 4/7; ρ vs the 3600 s reference falls to 0.565.
   This **withdraws a P1 README claim** that invariance held — that earlier test used
   5 coarse candidates where ties were unlikely, and it does not generalise.
5. **Targeted attack does not universally dominate random failure.** It dominates on
   chokepoint topologies and loses on homogeneous lattices. Retained; it is the result
   the removed clamp existed to suppress.
6. **No method ever made a network worse.** `frac_lt_0 = 0.00` in every cell of both
   scenario sets.

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
- 51 tests + 1 documented xfail pass in both cache modes; clean-clone build verified.
- **Under a connectivity-restoration objective on the tested synthetic topologies,**
  the system's intervention proposer does not outperform shortest-gap closure.
- **At k=5 on a 13,486-node sparse graph,** top-10 betweenness overlap with exact is
  0.34 — a re-demonstration of a known phenomenon, not a new one.

Every empirical claim must carry: *synthetic graphs only; no real road network; no
Bengaluru measurement.*

---

## 6. Claims that must not be made

Already removed in P1 and to stay removed: IoU 0.73, F1 0.81, "+12% occlusion
retention", Precision@5 = 4/5, Precision@10 = 8/10, "13,486 intersections",
"16,000+ road segments", "44,552 residents impacted", "24 emergency facilities",
"312 vulnerable intersections", "answers that in 3 seconds", the "(Confidence: 78%)"
cascade extrapolation, fabricated infrastructure labels, and the ₹/$ cost estimates.

Additionally prohibited from here on:

- **Any Bengaluru measurement.** Overpass was unreachable; no real graph was used.
  The 13,486-node object is a topology proxy with uniform placeholder weights and no
  coordinates.
- **"Intervention rankings are invariant across finite RI penalties."** Withdrawn —
  contradicted by A7 (0/7 cases).
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

### Commits (branch `claude/youthful-allen-j77qi5`)

| Commit | Content |
|---|---|
| `bd5a916` | P0 — clamps removed, route crash fixed, RI explicit, ML quarantined |
| `f8f2324` | P1 — provenance, fingerprinting, build hygiene, core tests |
| `a1e889e` | P1 completion — UI provenance, surviving RGS clamps, claim audit |
| `5a5ae27` | P2.0/P2.2 partial — scripts, frozen scenarios, A5 synth, A7 |
| `658e2a0` | ignore raw outputs while in flight |
| `7a61031` | P2.0 complete — A5 on the 13,486-node proxy |
| `1819cec` | P2.2 — raw intervention outputs + pre-registered aggregate |
| `13bfc08` | P2.2 — post-hoc relative-k aggregate (separate, never merged) |
| `2c336b6` | Post-mortem — H2 mechanism + A5 ρ/top-K trap |

### Experimental artifacts (SHA-256, first 16 hex)

| Artifact | Hash | Size |
|---|---|---|
| `scenarios/scenarios.json` (1,212, pre-registered) | `b39ce17b95c6ec43` | 370 KB |
| `scenarios/scenarios_relative.json` (1,414, post-hoc) | `e896c598f3647b30` | 736 KB |
| `results/a5_k_sensitivity_proxy.json` | `d2ff66ba1e28dd10` | 13 KB |
| `results/a5_k_sensitivity_synth.json` | `911c0736c112659a` | 27 KB |
| `results/a7_ri_penalty.json` | `1f640ea12ebc2590` | 24 KB |
| `results/interventions_raw.jsonl` (19,392 rec) | `05c4bd4e6ffa6fdc` | 10.5 MB |
| `results/interventions_raw_relative.jsonl` (24,240 rec) | `47c49de0445720b3` | 13.2 MB |
| `results/interventions_aggregate_absolute.json` | `548415c6c7a0d6b4` | 23 KB |
| `results/interventions_aggregate_relative.json` | `5cf42bbe2d2921dd` | 23 KB |
| `results/postmortem_i1_vs_i3.json` | `bfe501923d310c31` | 85 KB |

> The scenario files also carry an internal `sha256_of_body` (`c222fbd2e9b56390`,
> `2e8dd6747a4f8ded`) computed over the payload *excluding* that field; the runner
> verifies it before executing. Both differ from the whole-file hashes above by
> construction. Both verify.

### Reproducibility assets

`experiments/04_gen_scenarios.py`, `05_run_interventions.py`,
`06_ablation_a5_k_sensitivity.py`, `06_ablation_a7_ri_penalty.py`, `07_aggregate.py`,
`08_postmortem_i1_vs_i3.py` · `PREREGISTRATION_DEVIATIONS.md` (D1–D7, including two
self-reported design errors) · `POSTMORTEM_H2.md` · `POSTMORTEM_A5.md` ·
`CLAIMS.md` · `backend/data/README.md` · `backend/tests/` (51 + 1 xfail) ·
master seed `20260915`, bootstrap 10,000 reps seeded, `STRICT_GRAPH_CACHE` mode.

---

## 9. Possible future directions

**All UNVALIDATED. None implemented, none tested, none endorsed.** Listed only so the
reasoning is not lost.

1. **Objective-matched criticality.** For a connectivity objective, block-cut-tree
   measures (articulation points, OD-pairs-disconnected-on-removal) are the
   theoretically matched quantity; betweenness measures shortest-path flow. *Untested,
   and it would test our own system's measure choice, not a general claim.*
2. **Preventive node protection.** Blocked at the G1/G2 gates (no real graph, no
   empirically-grounded disruption distribution) and separately assessed as a
   replication of Holme et al. (2002) and Jenelius et al. (2006).
3. **Exact cached betweenness in production.** Exact costs 504 s at 13,486 nodes and
   centrality is already precomputed and disk-cached, so the k=5 "timeout" rationale
   does not hold. *An engineering change, not research; deliberately not made while an
   evaluation of the current configuration is on record.*
4. **A real graph.** Every empirical limitation traces to this. Unobtainable in the
   development environment; would require running `scripts/download_data.py` with
   Overpass access and recording the fingerprint.
5. **Technical report rather than a paper.** Positioning the work as a worked example
   of known evaluation pitfalls, citing Geisberger et al. and Webber et al. as prior
   art, with no novelty claim.

---

**Route Resilience is frozen as a research artifact.** Experimental results are not
to be modified, re-run, or reframed.
