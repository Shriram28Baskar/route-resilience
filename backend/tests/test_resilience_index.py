"""
Resilience Index behaviour and its penalty-free decomposition.

These tests protect scientific claims, not lines of code. Each one corresponds
to a statement the project would have to defend in review.
"""
import networkx as nx
import pytest

from app.simulation.ablation import ablate_nodes
from app.simulation.resilience import (
    DEFAULT_PENALTY_S,
    compute_resilience_index,
)


def test_unperturbed_graph_has_ri_one(chokepoint):
    """Claim: RI == 1 means 'no degradation'."""
    r = compute_resilience_index(chokepoint, chokepoint)
    assert r["resilience_index"] == pytest.approx(1.0)
    assert r["unreachable_fraction"] == 0.0
    assert r["reachable_path_inflation"] == pytest.approx(1.0)


def test_ri_decreases_monotonically_under_nested_ablation(chokepoint):
    """
    Claim: RI measures damage. Removing a superset of nodes cannot make the
    network look healthier.
    """
    bridges = chokepoint.graph["bridge_nodes"]
    prev = 1.0
    for k in range(1, len(bridges) + 1):
        r = compute_resilience_index(chokepoint, ablate_nodes(chokepoint, bridges[:k]))
        ri = r["resilience_index"]
        assert ri <= prev + 1e-9, f"RI rose from {prev} to {ri} when ablating {k} nodes"
        prev = ri


def test_severing_the_network_does_not_improve_ri(chokepoint):
    """
    Regression: the naive implementation (drop unreachable pairs) reports an
    IMPROVED average path length after partitioning. The penalty exists to
    prevent exactly that.
    """
    bridges = chokepoint.graph["bridge_nodes"]
    severed = ablate_nodes(chokepoint, bridges)
    r = compute_resilience_index(chokepoint, severed)
    assert r["resilience_index"] < 1.0
    assert r["unreachable_fraction"] > 0.0
    assert r["disconnected"] is True


def test_ri_floor_equals_baseline_over_penalty(chokepoint):
    """
    Claim (and limitation): RI is bounded below by baseline_mean / penalty_s.
    That floor is network-dependent, which is why RI is not cross-network
    comparable and why the API says so.
    """
    r = compute_resilience_index(chokepoint, chokepoint)
    expected_floor = r["baseline_avg_path"] / DEFAULT_PENALTY_S
    assert r["ri_floor"] == pytest.approx(expected_floor, rel=1e-4)
    assert r["ri_is_cross_network_comparable"] is False


def test_penalty_is_reported_and_honoured(chokepoint):
    """A metric conditional on a constant must report that constant."""
    bridges = chokepoint.graph["bridge_nodes"]
    perturbed = ablate_nodes(chokepoint, bridges)
    r1 = compute_resilience_index(chokepoint, perturbed, penalty_s=1800.0)
    r2 = compute_resilience_index(chokepoint, perturbed, penalty_s=7200.0)
    assert r1["penalty_s"] == 1800.0
    assert r2["penalty_s"] == 7200.0
    # A harsher penalty must not make the same damage look milder.
    assert r2["resilience_index"] < r1["resilience_index"]


@pytest.mark.parametrize("graph_name", ["grid", "chokepoint"])
def test_ablation_severity_ranking_is_stable_across_finite_penalties(graph_name, request):
    """
    Ranks five DISRUPTION SCENARIOS (disjoint triples of high-betweenness nodes,
    each ABLATED) by the RI they produce, and checks that ordering is stable
    across finite penalties.

    READ THE NAME CAREFULLY. This measures the ranking of DAMAGE, not the
    ranking of INTERVENTIONS. Until the audit this test was named
    `test_intervention_ranking_is_invariant_across_finite_penalties` and its
    docstring called the ablation sets "candidate interventions". It was cited in
    README.md and CLAIMS.md as evidence that "intervention rankings are invariant
    across finite RI penalties". That citation was wrong twice over: the test
    never ranked interventions, and the claim itself is FALSE -- experiment A7
    ranks 20 candidate EDGE ADDITIONS and finds the ranking identical in 0 of 8
    cases (experiments/results/a7_ri_penalty.json).

    What this test still establishes, and all it establishes: RI's ordering of
    damage scenarios does not flip with the penalty constant on these two
    fixtures. That is a much weaker statement and supports no recommendation.
    """
    G = request.getfixturevalue(graph_name)
    from app.graph_pipeline.centrality import compute_betweenness

    bc = compute_betweenness(G)
    ranked = [n for n, _ in sorted(bc.items(), key=lambda x: x[1], reverse=True) if n in G]
    ablation_sets = [ranked[i * 3:(i * 3) + 3] for i in range(5)]

    rankings = set()
    for penalty in (1800.0, 3600.0, 7200.0):
        scores = [
            compute_resilience_index(G, ablate_nodes(G, c), penalty_s=penalty)["resilience_index"]
            for c in ablation_sets
        ]
        assert all(s is not None for s in scores)
        rankings.add(tuple(i for i, _ in sorted(enumerate(scores), key=lambda x: x[1])))

    assert len(rankings) == 1, (
        f"Ranking of ablation scenarios on '{graph_name}' changed with the penalty "
        f"constant: {rankings}."
    )


@pytest.mark.parametrize("graph_name", ["grid", "chokepoint"])
def test_intervention_ranking_is_not_invariant_across_finite_penalties(graph_name, request):
    """
    The claim README.md and CLAIMS.md used to make -- "intervention rankings are
    invariant across finite RI penalties" -- is FALSE, and this test pins the
    refutation so it cannot be silently reinstated.

    Construction mirrors experiment A7 (experiments/06_ablation_a7_ri_penalty.py):
    build a bounded, deterministic pool of candidate EDGE ADDITIONS, score each
    by the RI of the hardened graph under an identical ablation, and compare the
    orderings across penalties.

    A7 result on 4 graphs x 2 disruptions: full ranking identical in 0 of 8
    cases, top-1 stable in 3 of 8, minimum defined Spearman rho vs the 3600 s
    reference 0.390. This test reproduces the same failure at fixture scale.

    If this test ever starts failing, the correct response is to RE-RUN A7 and
    report what changed -- not to restore the withdrawn invariance claim.
    """
    G = request.getfixturevalue(graph_name)
    from app.graph_pipeline.centrality import compute_betweenness

    bc = compute_betweenness(G)
    ablated = [n for n, _ in sorted(bc.items(), key=lambda x: x[1], reverse=True)[:10] if n in G]

    perturbed = ablate_nodes(G, ablated)
    comps = sorted(nx.connected_components(perturbed), key=len, reverse=True)
    pool = []
    if len(comps) > 1:
        a = sorted(comps[0], key=lambda x: -perturbed.degree(x))[:10]
        b = sorted(comps[1], key=lambda x: -perturbed.degree(x))[:10]
        pool = [(u, v) for u in a for v in b if not G.has_edge(u, v)]
    if len(pool) < 20:
        cand = sorted(perturbed.nodes(), key=lambda x: -perturbed.degree(x))[:24]
        pool += [(u, v) for i, u in enumerate(cand) for v in cand[i + 1:]
                 if not G.has_edge(u, v)]
    candidates = pool[:20]
    assert len(candidates) >= 10, "pool too small to rank meaningfully"

    rankings = {}
    for penalty in (900.0, 1800.0, 3600.0, 7200.0, 14400.0):
        scores = []
        for u, v in candidates:
            hardened = G.copy()
            hardened.add_edge(u, v, length=500.0, weight=500.0, speed_kph=50.0,
                              time_s=36.0, highway="tertiary")
            scores.append(compute_resilience_index(
                G, ablate_nodes(hardened, ablated), penalty_s=penalty)["resilience_index"])
        assert all(s is not None for s in scores)
        rankings[penalty] = tuple(i for i, _ in sorted(enumerate(scores), key=lambda x: -x[1]))

    assert len(set(rankings.values())) > 1, (
        f"Intervention ranking on '{graph_name}' was IDENTICAL across all five "
        f"penalties. That contradicts A7 (0/8 identical). Re-run A7 and report the "
        f"discrepancy; do NOT reinstate the withdrawn invariance claim on this basis."
    )


def test_infinite_penalty_is_degenerate(chokepoint):
    """
    Documented limitation, asserted so it cannot silently change: at an
    effectively infinite penalty every perturbation scores 0 and the metric
    stops discriminating.
    """
    bridges = chokepoint.graph["bridge_nodes"]
    a = compute_resilience_index(chokepoint, ablate_nodes(chokepoint, bridges[:1]), penalty_s=1e9)
    b = compute_resilience_index(chokepoint, ablate_nodes(chokepoint, bridges), penalty_s=1e9)
    assert a["resilience_index"] == pytest.approx(0.0, abs=1e-3)
    assert b["resilience_index"] == pytest.approx(0.0, abs=1e-3)


# ── penalty-free decomposition ────────────────────────────────────────────────

def test_decomposition_is_independent_of_penalty(chokepoint):
    """
    Claim: unreachable_fraction and reachable_path_inflation can be used for
    cross-network statements because they do not depend on the constant.
    """
    bridges = chokepoint.graph["bridge_nodes"]
    perturbed = ablate_nodes(chokepoint, bridges)
    results = [compute_resilience_index(chokepoint, perturbed, penalty_s=p)
               for p in (1800.0, 3600.0, 7200.0, 1e9)]
    assert len({r["unreachable_fraction"] for r in results}) == 1
    assert len({r["reachable_path_inflation"] for r in results}) == 1


def test_decomposition_separates_severance_from_slowdown(chokepoint):
    """
    Claim: a low RI does NOT imply longer journeys. Cutting the bridge chain
    severs pairs outright while leaving surviving pairs untouched, and the
    decomposition must expose that difference.
    """
    bridges = chokepoint.graph["bridge_nodes"]
    r = compute_resilience_index(chokepoint, ablate_nodes(chokepoint, bridges))
    assert r["resilience_index"] < 0.3               # looks catastrophic
    assert r["unreachable_fraction"] > 0.3           # because pairs are severed
    assert r["reachable_path_inflation"] == pytest.approx(1.0, abs=0.05)  # not slower


def test_pair_accounting_is_consistent(chokepoint):
    bridges = chokepoint.graph["bridge_nodes"]
    r = compute_resilience_index(chokepoint, ablate_nodes(chokepoint, bridges))
    assert 0 <= r["pairs_severed"] <= r["pairs_evaluated"]
    assert r["unreachable_fraction"] == pytest.approx(
        r["pairs_severed"] / r["pairs_evaluated"], rel=1e-6
    )


def test_ri_is_deterministic(chokepoint):
    """Sampling is seeded; two identical calls must agree exactly."""
    bridges = chokepoint.graph["bridge_nodes"]
    a = compute_resilience_index(chokepoint, ablate_nodes(chokepoint, bridges[:2]))
    b = compute_resilience_index(chokepoint, ablate_nodes(chokepoint, bridges[:2]))
    assert a["resilience_index"] == b["resilience_index"]
    assert a["unreachable_fraction"] == b["unreachable_fraction"]
