from __future__ import annotations

import asyncio

import pytest

from desktop_bridge.method_policy import MethodPolicy, method_policy
from shiori_sdk.rpc import Concurrency
from desktop_bridge.request_dispatcher import BridgeRequestDispatcher


@pytest.mark.asyncio
async def test_runtime_transaction_does_not_block_control_or_new_request_responses():
    dispatcher = BridgeRequestDispatcher(max_concurrency=1)
    started = asyncio.Event()
    release = asyncio.Event()
    responses = asyncio.Queue()

    async def apply():
        started.set()
        await release.wait()

    dispatcher.submit({"method": "runtime.apply"}, apply)
    try:
        await asyncio.wait_for(started.wait(), 0.2)
        for method in ("health", "chat.cancel", "chat.send"):
            dispatcher.submit(
                {"method": method}, lambda method=method: responses.put(method)
            )
        completed = [await asyncio.wait_for(responses.get(), 0.2) for _ in range(3)]
        assert set(completed) == {"health", "chat.cancel", "chat.send"}
    finally:
        release.set()
        await dispatcher.aclose()


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

    dispatcher.submit({"method": "models.test"}, _mutation)
    await mutation_started.wait()
    dispatcher.submit({"method": "health"}, _health)

    await asyncio.wait_for(health_completed.wait(), timeout=0.2)
    release_mutation.set()
    await dispatcher.aclose()


@pytest.mark.asyncio
async def test_control_mutation_runs_while_integration_lane_is_busy() -> None:
    dispatcher = BridgeRequestDispatcher(max_concurrency=2)
    generation_started = asyncio.Event()
    release_generation = asyncio.Event()
    cancel_completed = asyncio.Event()

    async def _generate() -> None:
        generation_started.set()
        await release_generation.wait()

    async def _cancel() -> None:
        cancel_completed.set()

    dispatcher.submit({"method": "models.test"}, _generate)
    await generation_started.wait()
    dispatcher.submit({"method": "chat.cancel"}, _cancel)

    await asyncio.wait_for(cancel_completed.wait(), timeout=0.2)
    release_generation.set()
    await dispatcher.aclose()


@pytest.mark.asyncio
async def test_regeneration_uses_the_bounded_integration_lane() -> None:
    dispatcher = BridgeRequestDispatcher(
        max_concurrency=2,
        integration_concurrency=2,
    )
    both_started = asyncio.Event()
    release = asyncio.Event()
    active = 0

    async def _regenerate() -> None:
        nonlocal active
        active += 1
        if active == 2:
            both_started.set()
        await release.wait()
        active -= 1

    dispatcher.submit({"method": "models.test"}, _regenerate)
    dispatcher.submit({"method": "models.test"}, _regenerate)

    await asyncio.wait_for(both_started.wait(), timeout=0.2)
    release.set()
    await dispatcher.aclose()


@pytest.mark.asyncio
async def test_plugin_submission_uses_its_declared_integration_lane() -> None:
    def resolver(method: str) -> MethodPolicy:
        if method == "plugin.demo.continue":
            return MethodPolicy(concurrency=Concurrency.INTEGRATION)
        return method_policy(method)

    dispatcher = BridgeRequestDispatcher(max_concurrency=2, policy_resolver=resolver)
    run_started = asyncio.Event()
    release_run = asyncio.Event()
    role_update_completed = asyncio.Event()

    async def _continue_plugin() -> None:
        run_started.set()
        await release_run.wait()

    async def _update_role() -> None:
        role_update_completed.set()

    dispatcher.submit({"method": "plugin.demo.continue"}, _continue_plugin)
    try:
        await asyncio.wait_for(run_started.wait(), timeout=0.2)
        dispatcher.submit({"method": "roles.update"}, _update_role)
        await asyncio.wait_for(role_update_completed.wait(), timeout=0.2)
    finally:
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
async def test_injected_policy_resolver_overrides_the_static_table() -> None:
    # generation/bridge 服务按 DI 而非全局字典把 plugin.* 方法策略动态注入分发器
    calls: list[str] = []

    def resolver(method: str) -> MethodPolicy:
        calls.append(method)
        return MethodPolicy(concurrency=Concurrency.READ_ONLY)

    dispatcher = BridgeRequestDispatcher(policy_resolver=resolver)
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
        dispatcher.submit({"method": "plugin.demo.write"}, _read)
    await asyncio.sleep(0)

    # 静态表会把 plugin.demo.write 当作串行 mutation；注入的 resolver 证明它确实生效
    assert peak == 4
    assert calls.count("plugin.demo.write") == 4
    release.set()
    await dispatcher.aclose()


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
