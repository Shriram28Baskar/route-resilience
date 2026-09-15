"""Regression coverage for the three production audit blockers."""
import asyncio
import struct
import time

import networkx as nx
from unittest.mock import patch

from app.api.citizens import CitizenReportRequest, submit_citizen_report
from app.simulation.disaster_state import citizen_evidence_store
from app.simulation.projected_flood_exposure import predict_flood_exposure_eta
from app.simulation.recommendations import (
    cache_recommendations,
    get_cached_recommendations,
)
from app.simulation.topography import _read_hgt_bilinear
from app.integrations.alerts import broadcast_heartbeat


def _eta_graph(elevation: float = 880.004) -> nx.Graph:
    graph = nx.Graph()
    graph.add_node(1, x=77.61, y=12.93, elevation=elevation)
    return graph


def test_cached_tactical_snapshot_is_nonblocking_and_isolated():
    """The observation path can read tactics without entering the optimiser."""
    cache_recommendations([{"title": "Cached bypass", "target_nodes": ["1", "2"]}])
    started = time.perf_counter()
    with patch("app.simulation.recommendations.generate_recommendations") as optimise:
        snapshot = get_cached_recommendations()
    assert time.perf_counter() - started < 0.05
    optimise.assert_not_called()
    assert snapshot[0]["title"] == "Cached bypass"
    snapshot[0]["title"] = "caller mutation"
    assert get_cached_recommendations()[0]["title"] == "Cached bypass"


def test_heartbeat_broadcast_is_safe_without_connected_websocket_clients():
    """A failed observation can retain state even when no dashboard is connected."""
    asyncio.run(broadcast_heartbeat({"type": "LOOP_HEARTBEAT", "sequence_no": 1}))


def test_citizen_submission_sets_existing_loop_trigger_without_running_cycle():
    """A report wakes the scheduler event; it never invokes a second cycle."""
    graph = nx.Graph()
    graph.add_node(10, x=77.61, y=12.93, elevation=881.0)
    trigger = asyncio.Event()
    citizen_evidence_store.clear_all()

    async def submit():
        with patch("app.api.citizens.GraphStore.get_osm_fallback", return_value=graph), \
             patch("app.api.citizens._wake_citizen_loop", side_effect=trigger.set) as wake_loop:
            response = await submit_citizen_report(CitizenReportRequest(
                lat=12.93, lon=77.61, message="Road is flooded and water is rising",
            ))
        return response, wake_loop

    response, wake_loop = asyncio.run(submit())
    assert response.status_code == 200
    assert trigger.is_set()
    wake_loop.assert_called_once_with()
    assert len(citizen_evidence_store.get_recent()) == 1
    citizen_evidence_store.clear_all()


def test_serialized_citizen_transitions_queue_a_follow_up_cycle():
    """A trigger raised mid-cycle queues a later cycle instead of concurrent ACT."""
    async def exercise():
        from app.simulation.loop_triggers import wait_for_loop_wakeup
        loop_lock = asyncio.Lock()
        manual_trigger = asyncio.Event()
        citizen_trigger = asyncio.Event()
        active = 0
        maximum_active = 0
        calls = 0

        async def transition():
            nonlocal active, maximum_active, calls
            async with loop_lock:
                active += 1
                maximum_active = max(maximum_active, active)
                calls += 1
                if calls == 1:
                    # This represents a report arriving while ACT is in flight.
                    citizen_trigger.set()
                await asyncio.sleep(0.01)
                active -= 1

        citizen_trigger.set()
        for _ in range(2):
            await asyncio.wait_for(
                wait_for_loop_wakeup(manual_trigger, citizen_trigger, 60), timeout=1.0,
            )
            manual_trigger.clear()
            citizen_trigger.clear()
            await transition()

        assert calls == 2
        assert maximum_active == 1

    asyncio.run(exercise())


def test_bilinear_srtm_lookup_is_continuous(tmp_path):
    """Interpolating integral DEM cells yields a local continuous elevation."""
    hgt = tmp_path / "N12E077.hgt"
    hgt.write_bytes(struct.pack(">hhhh", 100, 101, 102, 103))
    assert _read_hgt_bilinear(str(hgt), 12.5, 77.5) == 101.5


def test_eta_is_present_and_monotonic_for_realistic_to_high_rainfall():
    """ETA decreases monotonically with the same continuous terrain delta."""
    graph = _eta_graph()
    realistic = predict_flood_exposure_eta(graph, 880.0, rainfall_rate_mm_h=5.0)
    moderate = predict_flood_exposure_eta(graph, 880.0, rainfall_rate_mm_h=20.0)
    controlled_high = predict_flood_exposure_eta(graph, 880.0, rainfall_rate_mm_h=60.0)

    assert all((realistic, moderate, controlled_high))
    eta_realistic = realistic[0]["eta_minutes"]
    eta_moderate = moderate[0]["eta_minutes"]
    eta_high = controlled_high[0]["eta_minutes"]
    assert 0 < eta_high < eta_moderate < eta_realistic <= 90
    assert realistic[0]["data_type"] == "EXTRAPOLATED"
    assert realistic[0]["projection_basis"] == "linear_effective_runoff_persistence"
