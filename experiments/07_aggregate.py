#!/usr/bin/env python3
"""
P2.2 step 3 — aggregate raw intervention records into tables + statistics.

Reads only committed raw JSONL. Computes nothing that was not pre-registered:

  PRIMARY   delta_unreachable_fraction, all scenarios, per (method, budget)
  PAIRED    I1 (Route Resilience) vs each baseline on IDENTICAL scenarios
            -> Wilcoxon signed-rank, Cliff's delta, paired bootstrap CI
  NEGATIVE  fraction of scenarios with delta <= 0 and delta < 0, always shown

A secondary stratification to scenarios that actually partitioned the graph is
reported alongside, never instead of, the primary. Restricting to partitioned
scenarios would flatter every method, so the all-scenario figure leads.
"""
from __future__ import annotations

import collections
import json
import math
import os
import random
import statistics as st
import sys
from typing import Dict, List, Tuple

RESULTS = os.path.join(os.path.dirname(__file__), "results")
BOOT = 10_000
BOOT_SEED = 20260915
METHODS = ["I1_route_resilience", "I2_random", "I3_nearest_gap",
           "I4_highest_degree", "I5_oracle"]
PRIMARY = "delta_unreachable_fraction"


def load(paths: List[str]) -> List[Dict]:
    rows = []
    for p in paths:
        with open(p) as f:
            rows += [json.loads(l) for l in f if l.strip()]
    return rows


# ── statistics ────────────────────────────────────────────────────────────────

def boot_ci(vals, stat=st.median, n=BOOT, seed=BOOT_SEED, alpha=0.05):
    if not vals:
        return (None, None)
    rng = random.Random(seed)
    k = len(vals)
    reps = []
    for _ in range(n):
        reps.append(stat([vals[rng.randrange(k)] for _ in range(k)]))
    reps.sort()
    return (reps[int(alpha / 2 * n)], reps[int((1 - alpha / 2) * n)])


def cliffs_delta(a, b):
    """Non-parametric effect size. |d|: .147 small, .33 medium, .474 large."""
    if not a or not b:
        return None
    gt = lt = 0
    for x in a:
        for y in b:
            if x > y:
                gt += 1
            elif x < y:
                lt += 1
    return (gt - lt) / (len(a) * len(b))


def wilcoxon(pairs: List[Tuple[float, float]]):
    """Paired signed-rank. Returns (statistic, p, n_nonzero) or None."""
    diffs = [x - y for x, y in pairs if x != y]
    n = len(diffs)
    if n < 6:
        return None
    try:
        from scipy.stats import wilcoxon as w
        r = w([x for x, y in pairs], [y for x, y in pairs],
              zero_method="wilcox", alternative="two-sided")
        return {"statistic": float(r.statistic), "p_value": float(r.pvalue), "n_nonzero": n}
    except Exception:
        return None


def paired_boot_median_diff(pairs, n=BOOT, seed=BOOT_SEED):
    rng = random.Random(seed)
    k = len(pairs)
    reps = []
    for _ in range(n):
        idx = [rng.randrange(k) for _ in range(k)]
        reps.append(st.median([pairs[i][0] - pairs[i][1] for i in idx]))
    reps.sort()
    return (reps[int(0.025 * n)], reps[int(0.975 * n)], st.median([a - b for a, b in pairs]))


# ── aggregation ───────────────────────────────────────────────────────────────

def describe(vals: List[float]) -> Dict:
    if not vals:
        return {"n": 0}
    lo, hi = boot_ci(vals)
    return {
        "n": len(vals),
        "median": round(st.median(vals), 8),
        "median_ci95": [round(lo, 8), round(hi, 8)],
        "mean": round(st.mean(vals), 8),
        "max": round(max(vals), 8),
        "frac_le_0": round(sum(1 for v in vals if v <= 0) / len(vals), 4),
        "frac_lt_0": round(sum(1 for v in vals if v < 0) / len(vals), 4),
        "frac_gt_0": round(sum(1 for v in vals if v > 0) / len(vals), 4),
    }


def main():
    # The pre-registered (absolute-k) and post-hoc (relative-k) scenario sets are
    # reported SEPARATELY. Merging them would let the post-hoc extension dilute
    # or inflate the pre-registered result.
    which = sys.argv[1] if len(sys.argv) > 1 else "absolute"
    assert which in ("absolute", "relative")
    paths = [os.path.join(RESULTS, f) for f in sorted(os.listdir(RESULTS))
             if f.startswith("interventions_raw") and f.endswith(".jsonl")
             and (("_relative" in f) == (which == "relative"))]
    if not paths:
        sys.exit(f"no raw intervention files for set '{which}'")
    rows = load(paths)
    print(f"[{which} scenario set] loaded {len(rows)} raw records from "
          f"{len(paths)} file(s): {[os.path.basename(p) for p in paths]}")

    # context: how often did the disruption actually partition the graph?
    base = {r["scenario_id"]: r for r in rows if r["method"] == "I0_none"}
    partitioned = {sid for sid, r in base.items() if (r.get("partition_count") or 1) > 1}
    print(f"scenarios: {len(base)}  partitioned by the disruption: {len(partitioned)} "
          f"({len(partitioned)/max(1,len(base)):.1%})")

    out: Dict = {
        "experiment": "P2.2_interventions",
        "scenario_set": which,
        "scenario_set_status": ("pre-registered" if which == "absolute"
                                else "POST-HOC extension, see PREREGISTRATION_DEVIATIONS.md D7"),
        "primary_endpoint": PRIMARY,
        "n_scenarios": len(base),
        "n_partitioned": len(partitioned),
        "bootstrap_reps": BOOT,
        "bootstrap_seed": BOOT_SEED,
        "tables": {},
    }

    for subset_name, sids in (("all_scenarios", set(base)),
                              ("partitioned_only", partitioned)):
        table = {}
        for m in METHODS:
            for b in sorted({r["budget_m"] for r in rows if r["method"] == m}):
                vals = [r[PRIMARY] for r in rows
                        if r["method"] == m and r["budget_m"] == b
                        and r["scenario_id"] in sids]
                prop = [r for r in rows if r["method"] == m and r["budget_m"] == b
                        and r["scenario_id"] in sids]
                d = describe(vals)
                d["proposal_rate"] = round(
                    sum(1 for r in prop if r["n_edges_added"] > 0) / max(1, len(prop)), 4)
                d["mean_length_used_m"] = round(
                    st.mean([r["length_used_m"] for r in prop]) if prop else 0.0, 1)
                table[f"{m}|{int(b)}m"] = d
        out["tables"][subset_name] = table

    # ── paired comparisons: I1 vs each baseline, identical scenarios ──────────
    comps = {}
    for b in sorted({r["budget_m"] for r in rows if r["method"] == "I1_route_resilience"}):
        idx = collections.defaultdict(dict)
        for r in rows:
            if r["budget_m"] == b and r["method"] in METHODS:
                idx[r["scenario_id"]][r["method"]] = r[PRIMARY]
        for other in [m for m in METHODS if m != "I1_route_resilience"]:
            pairs = [(v["I1_route_resilience"], v[other]) for v in idx.values()
                     if "I1_route_resilience" in v and other in v]
            if not pairs:
                continue
            lo, hi, med = paired_boot_median_diff(pairs)
            comps[f"I1_vs_{other}|{int(b)}m"] = {
                "n_pairs": len(pairs),
                "median_diff_I1_minus_other": round(med, 8),
                "median_diff_ci95": [round(lo, 8), round(hi, 8)],
                "ci_excludes_zero": bool(lo > 0 or hi < 0),
                "wilcoxon": wilcoxon(pairs),
                "cliffs_delta": (round(cliffs_delta([p[0] for p in pairs],
                                                    [p[1] for p in pairs]), 4)
                                 if len(pairs) <= 400 else "skipped_n_too_large"),
                "I1_wins": sum(1 for a, c in pairs if a > c),
                "other_wins": sum(1 for a, c in pairs if c > a),
                "ties": sum(1 for a, c in pairs if a == c),
            }
    out["paired_comparisons"] = comps

    # ── per scenario family and per graph ─────────────────────────────────────
    strat = {}
    for key in ("family", "graph"):
        for val in sorted({r[key] for r in rows}):
            for m in METHODS:
                vals = [r[PRIMARY] for r in rows
                        if r[key] == val and r["method"] == m and r["budget_m"] == 2000.0]
                if vals:
                    strat[f"{key}={val}|{m}|2000m"] = describe(vals)
    out["stratified_budget2000"] = strat

    path = os.path.join(RESULTS, f"interventions_aggregate_{which}.json")
    with open(path, "w") as f:
        json.dump(out, f, indent=1)
    print(f"wrote {path}")

    # ── console summary ──────────────────────────────────────────────────────
    for subset in ("all_scenarios", "partitioned_only"):
        print(f"\n=== PRIMARY: delta_unreachable_fraction — {subset} ===")
        print(f"{'method|budget':34s} {'n':>5s} {'median':>10s} {'mean':>10s} "
              f"{'>0':>6s} {'<=0':>6s} {'<0':>6s} {'prop':>6s}")
        for k, d in out["tables"][subset].items():
            if not d.get("n"):
                continue
            print(f"{k:34s} {d['n']:5d} {d['median']:10.6f} {d['mean']:10.6f} "
                  f"{d['frac_gt_0']:6.2f} {d['frac_le_0']:6.2f} {d['frac_lt_0']:6.2f} "
                  f"{d['proposal_rate']:6.2f}")

    print("\n=== PAIRED: I1 (Route Resilience) vs baselines ===")
    print(f"{'comparison':40s} {'n':>5s} {'med_diff':>11s} {'CI95':>26s} {'sig':>5s} "
          f"{'I1w':>5s} {'othw':>5s} {'tie':>5s}")
    for k, c in comps.items():
        ci = f"[{c['median_diff_ci95'][0]:+.6f},{c['median_diff_ci95'][1]:+.6f}]"
        print(f"{k:40s} {c['n_pairs']:5d} {c['median_diff_I1_minus_other']:+11.6f} "
              f"{ci:>26s} {'YES' if c['ci_excludes_zero'] else 'no':>5s} "
              f"{c['I1_wins']:5d} {c['other_wins']:5d} {c['ties']:5d}")


if __name__ == "__main__":
    main()
