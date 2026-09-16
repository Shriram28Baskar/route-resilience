# Frozen scenario sets — READ BEFORE TOUCHING

These two files are **evidence**. They are what `05_run_interventions.py` actually
executed, and their `sha256_of_body` is verified by the runner before every run.

| File | Records | Unique `scenario_id` | whole-file sha256 | payload `sha256_of_body` |
|---|---|---|---|---|
| `scenarios.json` (pre-registered, absolute k) | 1,212 | 1,212 | `b39ce17b95c6ec43…` | `c222fbd2e9b56390…` |
| `scenarios_relative.json` (post-hoc, size-relative k) | **1,515** | **1,414** | `e896c598f3647b30…` | `2e8dd6747a4f8ded…` |

## They cannot be regenerated

They were produced with

```python
seed = MASTER_SEED + hash((label, sname, k, i)) % 10_000_019
```

CPython salts `hash()` over tuples containing `str` on a per-process basis unless
`PYTHONHASHSEED` is pinned, and this repository never pinned it. Three successive
runs of the same expression gave `29728763`, `26872249`, `27689925`. Only the 12
`S5_targeted` scenarios (deterministic, betweenness top-k, no rng) were
regenerable — **1.0% of the pre-registered set.**

`04_gen_scenarios.py` now uses `hashlib.sha256` and is verified identical across
separate processes, but it **cannot reproduce these files**. It therefore refuses
to overwrite them and writes `*.regenerated.json` instead, unless you pass
`--overwrite-frozen`.

What the committed hash guarantees: the runner executed exactly the scenarios on
disk. What it does not guarantee: that those scenarios follow from the code.

## `scenarios_relative.json` contains 101 exact duplicates

`radial_25` has 25 nodes, so `max(2, round(f * 25))` maps the fractions
{0.05, 0.10, 0.20} to k ∈ {2, **2**, 5}. k=2 was generated twice. All 101
duplicate groups were verified byte-identical. The runner scored them twice, so
`interventions_raw_relative.jsonl` holds 24,240 rows for 22,624 unique
(scenario, method, budget) triples.

`07_aggregate.py` now drops the exact duplicates — aborting if any duplicate pair
disagrees — and reports `record_counts`. The generator deduplicates the k list.
**Neither file here was modified.** See `../PREREGISTRATION_DEVIATIONS.md` D8.

## The absolute set has 121 non-independent records

77 distinct `(graph, family, ablated-node-set)` signatures occur more than once,
totalling 121 excess records (10.0%). Different `(family, k, replicate)` cells can
draw the same node set on small graphs. Wilcoxon and the bootstrap both assume
independent pairs. **Disclosed, not corrected** — correcting a pre-registered
analysis after seeing results would be worse. See D10.
