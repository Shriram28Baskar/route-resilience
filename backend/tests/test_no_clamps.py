"""
Regression suite for the P0 clamp removals.

Each test pins a device that previously overwrote a measured result with a
predetermined one. These are the tests that make the project's numbers citable;
if one fails, a published figure is no longer trustworthy.
"""
import json
import random

import pytest

from app.graph_pipeline.centrality import compute_betweenness
from app.graph_pipeline.graph_build import GraphStore
from app.simulation.ablation import ablate_nodes
from app.simulation.cascade import _DAMPENING_FACTOR, run_cascade
from app.simulation.resilience import compute_resilience_index


def _body(resp):
    return json.loads(resp.body)


def _code_of(fn) -> str:
    """
    Source of `fn` with COMMENTS stripped (docstrings retained).

    Necessary because each removal is documented in a comment that quotes the
    deleted expression verbatim; a raw substring search would match the
    explanation rather than live code.
    """
    import inspect
    import io
    import tokenize

    src = inspect.getsource(fn)
    toks = [t for t in tokenize.generate_tokens(io.StringIO(src).readline)
            if t.type != tokenize.COMMENT]
    return " ".join(t.string for t in toks)


# ── /simulate/ablate/compare : random-failure clamp ───────────────────────────

def test_random_failure_ri_is_never_rewritten(grid):
    """
    The clamp raised random-failure RI to (betweenness_RI + 0.05) whenever
    random was MORE damaging, inverting the reported conclusion.

    The grid is the case that triggered it: a homogeneous lattice has no
    chokepoints, so random failure genuinely outperforms targeted attack.
    """
    from app.api.simulation import CompareRequest, ablate_compare
    GraphStore.set_healed(grid)

    for top_n in (3, 5, 10):
        reported = {s["strategy"]: s["resilience_index"]
                    for s in _body(ablate_compare(CompareRequest(top_n=top_n)))["strategies"]}

        # Recompute the random control exactly as the endpoint does.
        rng = random.Random(42)
        truth = compute_resilience_index(
            grid, ablate_nodes(grid, rng.sample(list(grid.nodes()), top_n))
        )["resilience_index"]

        assert reported["Random Failure"] == pytest.approx(truth, abs=1e-9), (
            f"n={top_n}: reported random RI {reported['Random Failure']} != "
            f"measured {truth}. A clamp has been reintroduced."
        )


def test_grid_reports_that_targeted_attack_does_not_dominate(grid):
    """
    A negative result must be publishable. On a homogeneous lattice the label
    must say targeted attack did not dominate, not paper over it.
    """
    from app.api.simulation import CompareRequest, ablate_compare
    GraphStore.set_healed(grid)

    strategies = _body(ablate_compare(CompareRequest(top_n=5)))["strategies"]
    worst = min(strategies, key=lambda s: s["resilience_index"])
    assert worst["strategy"] == "Random Failure"
    assert "did NOT dominate" in worst["winner_label"]


def test_chokepoint_reports_targeted_attack_dominating(chokepoint):
    """The complementary case: where targeted attack really does win, say so."""
    from app.api.simulation import CompareRequest, ablate_compare
    GraphStore.set_healed(chokepoint)

    strategies = _body(ablate_compare(CompareRequest(top_n=5)))["strategies"]
    worst = min(strategies, key=lambda s: s["resilience_index"])
    assert worst["strategy"] != "Random Failure"
    assert "Measured:" in worst["winner_label"]


# ── /simulate/ablate/prescribe : validation floor ─────────────────────────────

def test_prescribe_reports_measured_validation(chokepoint):
    """
    validated_ri was floored at attacked_ri + 0.025, so counterfactual
    validation could never report a failed intervention. The reported value
    must equal an independent recomputation.
    """
    from app.api.simulation import PrescribeRequest, ablate_prescribe
    GraphStore.set_healed(chokepoint)

    targets = chokepoint.graph["bridge_nodes"][:3]
    body = _body(ablate_prescribe(PrescribeRequest(
        ablated_node_ids=[str(t) for t in targets], max_recommendations=2)))

    assert body["suggestions"], "fixture should produce at least one suggestion"
    node_map = {str(n): n for n in chokepoint.nodes()}
    for s in body["suggestions"]:
        hardened = chokepoint.copy()
        hardened.add_edge(node_map[s["from_node"]], node_map[s["to_node"]],
                          time_s=90.0, length=750, highway="tertiary")
        honest = compute_resilience_index(
            chokepoint, ablate_nodes(hardened, targets))["resilience_index"]
        assert s["validated_ri"] == pytest.approx(honest, abs=1e-4), (
            "validated_ri does not match an independent recomputation; "
            "a validation floor has been reintroduced."
        )
        assert s["validation_outcome"] in ("improves", "no_change", "degrades")


def test_prescribe_can_express_a_failed_intervention():
    """
    A validation that cannot fail is not a validation. The outcome vocabulary
    must admit failure even if this fixture does not trigger it.
    """
    from app.api import simulation
    src = _code_of(simulation.ablate_prescribe)
    assert "NO_MEASURED_BENEFIT" in src
    assert "degrades" in src


# ── /simulate/cascade : forced decay ──────────────────────────────────────────

def test_cascade_dampening_is_off_by_default():
    assert _DAMPENING_FACTOR == 0.0, (
        "Non-zero dampening imposes monotonic decay on the result rather than "
        "measuring it. It must be an explicit, declared opt-in."
    )


def test_cascade_counts_are_not_truncated(chokepoint):
    """
    Each iteration was truncated to 65% of the previous count, manufacturing a
    decay curve. Real cascades on this fixture are non-monotonic.
    """
    steps = run_cascade(chokepoint, chokepoint.graph["bridge_nodes"][:2],
                        max_iterations=4, threshold=0.7)
    counts = [len(s["newly_stressed"]) for s in steps]
    for prev, cur in zip(counts, counts[1:]):
        cap = int(prev * 0.65)
        if cap > 0 and cur > 0:
            assert cur != cap or cur == prev, (
                f"iteration count {cur} lands exactly on the removed 65% cap "
                f"of {prev}; truncation may have been reintroduced"
            )
    assert any(s.get("dampening_factor") == 0.0 for s in steps)


def test_cascade_terminates_and_reports_why(chokepoint):
    """Every run must end with a machine-readable termination reason."""
    steps = run_cascade(chokepoint, chokepoint.graph["bridge_nodes"][:2],
                        max_iterations=5, threshold=0.7)
    assert steps, "cascade produced no steps"
    assert steps[-1]["termination_reason"] in (
        "natural_stabilization", "graph_too_small", "max_iterations_reached")
    assert len(steps) <= 5


def test_cascade_threshold_is_not_capped(chokepoint):
    """
    The threshold was capped at 98% 'so we always show some data'. A threshold
    high enough to select nothing must be allowed to select nothing.
    """
    steps = run_cascade(chokepoint, chokepoint.graph["bridge_nodes"][:1],
                        max_iterations=2, threshold=1.5)
    assert all(len(s["newly_stressed"]) == 0 for s in steps)


# ── /simulate/route : injected failure + crash ────────────────────────────────

def test_route_never_injects_an_unrequested_failure(chokepoint):
    """
    The guardrail ablated an extra node ON the computed path whenever the
    caller's ablation did not change the route, then attributed the detour to
    the caller's scenario.

    Pre-fix baseline, re-measured at commit 83e6b5e on this exact sweep
    (chokepoint fixture, seed 7, n=40): 27/40 = 68% injected a fabricated
    on-path failure, 8/40 = 20% raised an unhandled TypeError (HTTP 500).
    An earlier version of this docstring said 60% and 25%; neither reproduced.
    One fixture, one seed, n=40 -- read the proportions accordingly.
    """
    from app.api.simulation import RouteRequest, route
    GraphStore.set_healed(chokepoint)

    rng = random.Random(7)
    nodes = sorted(chokepoint.nodes())
    injected = crashes = 0
    for _ in range(40):
        s, t = rng.sample(nodes, 2)
        try:
            body = _body(route(RouteRequest(source_node=str(s), target_node=str(t),
                                            ablated_node_ids=[str(rng.choice(nodes))])))
        except TypeError:
            crashes += 1
            continue
        reported = {i["node_id"] for i in body["ablated_infra"]}
        assert len(reported) <= 1, "endpoint reported more ablations than requested"
        if any("Direct Route Failure" in str(i.get("type", "")) for i in body["ablated_infra"]):
            injected += 1

    assert injected == 0, f"{injected}/40 scenarios had a fabricated on-path failure"
    assert crashes == 0, f"{crashes}/40 scenarios crashed"


def test_route_returns_structured_result_when_severed(chokepoint):
    """
    Severing the origin-destination pair is the case the tool exists to model.
    It previously raised TypeError (None - float) and returned HTTP 500.
    """
    from app.api.simulation import RouteRequest, route
    GraphStore.set_healed(chokepoint)

    blocks = chokepoint.graph["bridge_nodes"]
    body = _body(route(RouteRequest(
        source_node=str(sorted(chokepoint.nodes())[0]),
        target_node=str(sorted(chokepoint.nodes())[-1]),
        ablated_node_ids=[str(n) for n in blocks],
    )))
    assert body["comparison_status"] == "severed_by_ablation"
    assert body["rerouted_reachable"] is False
    assert body["delta_distance_m"] is None
    assert body["baseline"]["reachable"] is True


def test_route_reports_no_fabricated_infrastructure_labels(chokepoint):
    """
    Labels such as "Hospital Access" were assigned round-robin by list index,
    with no facility layer joined to the graph.
    """
    from app.api.simulation import RouteRequest, route
    GraphStore.set_healed(chokepoint)

    nodes = sorted(chokepoint.nodes())
    body = _body(route(RouteRequest(source_node=str(nodes[0]), target_node=str(nodes[-1]),
                                    ablated_node_ids=[str(nodes[5]), str(nodes[6])])))
    for entry in body["ablated_infra"]:
        assert set(entry) == {"node_id", "resolved"}


def test_alternative_routes_are_measured_on_the_real_graph(path_graph):
    """
    A path graph has exactly one route. Alternatives are still returned (the
    penalisation heuristic finds nothing else), so their distances must at
    least be measured on the unpenalised graph, not the 4x-penalised copy.
    """
    from app.simulation.routing import compute_route
    r = compute_route(path_graph, 0, 5, num_alternatives=2)
    assert r["distance_m"] == pytest.approx(500.0)
    for alt in r["alternatives"]:
        assert alt["distance_m"] == pytest.approx(500.0), (
            "alternative distance was measured on the penalised graph"
        )


# ── /simulate/recommendations : RGS floors (found in the P1 claim audit) ──────
#
# These survived the P0 sweep because the comment read "ensure positive for
# demo", which none of the P0 grep patterns matched.

def test_recommendation_rgs_is_not_floored(chokepoint):
    """
    rgs was wrapped in max(rgs, 0.05) and max(rgs, 0.08), so every
    recommendation reported a positive resilience gain whether or not it helped.
    """
    from app.simulation import recommendations as R

    src = _code_of(R.generate_recommendations)
    assert "max ( rgs ," not in src, "an RGS floor has been reintroduced"

    recs = R.generate_recommendations(chokepoint)
    assert recs, "fixture should produce recommendations"
    for rec in recs:
        assert rec["cost_estimate"] is None, (
            "cost_estimate must stay null until a costing model exists"
        )
        assert "rgs_definition" in rec


@pytest.mark.xfail(reason="No fixture found that triggers the bypass branch: it "
                          "requires the top-2 betweenness nodes to be "
                          "non-adjacent, and high-betweenness nodes cluster. "
                          "The floor removal is verified by source inspection "
                          "below, but a negative bypass RGS is NOT empirically "
                          "demonstrated.", strict=False)
def test_bypass_branch_can_report_a_non_positive_gain(chokepoint):
    """Documented coverage gap — see the xfail reason."""
    from app.simulation.recommendations import generate_recommendations
    recs = generate_recommendations(chokepoint)
    assert any(r["type"] == "bypass" for r in recs)


def test_bypass_rgs_uses_a_common_baseline(chokepoint):
    """
    The bypass gain compared RI(G, attack) against RI(G_bypass, attack) — two
    indices with DIFFERENT baseline graphs, so their difference was not a gain.
    Both must now be measured against the same baseline.
    """
    from app.simulation import recommendations as R

    src = _code_of(R.generate_recommendations)
    assert "compute_resilience_index ( G_bypass ," not in src, (
        "bypass RI is being measured against its own hardened baseline again"
    )


def test_investment_projection_is_not_floored_at_baseline(chokepoint):
    """
    projected_ri was max(ri_base, ri_proj + rec["rgs"]): floored at the baseline
    AND double-counting a gain already contained in ri_proj.
    """
    from app.api import simulation

    src = _code_of(simulation.simulate_investment)
    assert "max ( ri_base" not in src, "the baseline floor has been reintroduced"
    assert 'rec [ "rgs" ]' not in src, "rgs is being double-counted again"
    assert "validation_outcome" in src


def test_investment_is_deterministic(chokepoint):
    """
    The reinforcement branch used an UNSEEDED random.choice, so two identical
    requests could return different numbers.
    """
    from app.api.simulation import SimulateInvestmentRequest, simulate_investment
    from app.graph_pipeline.graph_build import GraphStore

    GraphStore.set_healed(chokepoint)
    a = _body(simulate_investment(SimulateInvestmentRequest(recommendation_idx=0)))
    b = _body(simulate_investment(SimulateInvestmentRequest(recommendation_idx=0)))
    assert a["baseline_ri"] == b["baseline_ri"]
    assert a["projected_ri"] == b["projected_ri"]
    assert a["rgs"] == b["rgs"]
