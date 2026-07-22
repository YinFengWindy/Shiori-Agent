from __future__ import annotations

import asyncio

import pytest

from desktop_bridge.request_dispatcher import BridgeRequestDispatcher


@pytest.mark.asyncio
async def test_read_only_request_runs_while_mutation_lane_is_busy() -> None:
    dispatcher = BridgeRequestDispatcher(max_concurrency=2)
    mutation_started = asyncio.Event()
    release_mutation = asyncio.Event()
    health_completed = asyncio.Event()

    async def _mutation() -> None:
        mutation_started.set()
        await release_mutation.wait()

    async def _health() -> None:
        health_completed.set()

    dispatcher.submit({"method": "novelai.generate"}, _mutation)
    await mutation_started.wait()
    dispatcher.submit({"method": "health"}, _health)

    await asyncio.wait_for(health_completed.wait(), timeout=0.2)
    release_mutation.set()
    await dispatcher.aclose()


@pytest.mark.asyncio
async def test_control_mutation_runs_while_novelai_lane_is_busy() -> None:
    dispatcher = BridgeRequestDispatcher(max_concurrency=2)
    generation_started = asyncio.Event()
    release_generation = asyncio.Event()
    cancel_completed = asyncio.Event()

    async def _generate() -> None:
        generation_started.set()
        await release_generation.wait()

    async def _cancel() -> None:
        cancel_completed.set()

    dispatcher.submit({"method": "novelai.generate"}, _generate)
    await generation_started.wait()
    dispatcher.submit({"method": "chat.cancel"}, _cancel)

    await asyncio.wait_for(cancel_completed.wait(), timeout=0.2)
    release_generation.set()
    await dispatcher.aclose()


@pytest.mark.asyncio
async def test_world_run_submission_does_not_hold_global_mutation_lane() -> None:
    dispatcher = BridgeRequestDispatcher(max_concurrency=2)
    run_started = asyncio.Event()
    release_run = asyncio.Event()
    role_update_completed = asyncio.Event()

    async def _run_world() -> None:
        run_started.set()
        await release_run.wait()

    async def _update_role() -> None:
        role_update_completed.set()

    dispatcher.submit({"method": "worlds.advance"}, _run_world)
    await run_started.wait()
    dispatcher.submit({"method": "roles.update"}, _update_role)

    await asyncio.wait_for(role_update_completed.wait(), timeout=0.2)
    release_run.set()
    await dispatcher.aclose()


@pytest.mark.asyncio
async def test_mutation_requests_run_one_at_a_time() -> None:
    dispatcher = BridgeRequestDispatcher(max_concurrency=4)
    active = 0
    peak = 0

    async def _mutation() -> None:
        nonlocal active, peak
        active += 1
        peak = max(peak, active)
        await asyncio.sleep(0)
        active -= 1

    for method in ("roles.create", "roles.update", "chat.send"):
        dispatcher.submit({"method": method}, _mutation)

    await dispatcher.aclose()

    assert peak == 1


@pytest.mark.asyncio
async def test_read_only_requests_respect_concurrency_bound() -> None:
    dispatcher = BridgeRequestDispatcher(max_concurrency=2)
    active = 0
    peak = 0
    release = asyncio.Event()

    async def _read() -> None:
        nonlocal active, peak
        active += 1
        peak = max(peak, active)
        await release.wait()
        active -= 1

    for _ in range(4):
        dispatcher.submit({"method": "roles.list"}, _read)
    await asyncio.sleep(0)

    assert peak == 2
    release.set()
    await dispatcher.aclose()
