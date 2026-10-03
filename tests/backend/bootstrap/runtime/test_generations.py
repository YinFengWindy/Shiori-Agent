import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest

from bootstrap.runtime.generations import RuntimeCandidate, RuntimeRetention


def candidate():
    core = SimpleNamespace(
        stop=AsyncMock(),
        drain=AsyncMock(),
        assert_hot_unloadable=Mock(),
        memory_runtime=SimpleNamespace(aclose=AsyncMock()),
    )
    return RuntimeCandidate(1, core, SimpleNamespace(model="old"), published=True)


@pytest.mark.asyncio
async def test_retirement_waits_for_child_lease_and_closes_only_once():
    version = candidate()
    parent = version.acquire()
    child = parent.retain()
    await version.retire()
    await parent.release()
    version.core.stop.assert_not_awaited()
    assert child.config.model == "old"
    await child.release()
    await child.release()
    version.core.stop.assert_awaited_once()
    version.core.memory_runtime.aclose.assert_awaited_once()


@pytest.mark.asyncio
async def test_retirement_keeps_memory_alive_while_core_drains():
    version = candidate()
    entered = asyncio.Event()
    finish = asyncio.Event()

    async def drain(**kwargs):
        entered.set()
        await finish.wait()

    version.core.stop.side_effect = drain
    closing = asyncio.create_task(version.retire())
    await entered.wait()
    version.core.memory_runtime.aclose.assert_not_awaited()
    finish.set()
    await closing
    version.core.memory_runtime.aclose.assert_awaited_once()


@pytest.mark.asyncio
async def test_cleanup_failure_still_closes_memory_and_is_reported():
    version = candidate()
    version.core.stop.side_effect = RuntimeError("plugin cleanup failed")
    with pytest.raises(RuntimeError, match="plugin cleanup failed"):
        await version.retire()
    version.core.memory_runtime.aclose.assert_awaited_once()


@pytest.mark.asyncio
async def test_refused_retirement_preserves_bookkeeping_until_forced_shutdown():
    from bootstrap.runtime.generations import GenerationManager
    from agent.plugin_host import PluginRestartRequired

    version = candidate()
    version.core.assert_hot_unloadable.side_effect = PluginRestartRequired(["unsafe"])
    manager = GenerationManager()
    manager.start(version)
    with pytest.raises(PluginRestartRequired):
        await version.retire()
    with pytest.raises(PluginRestartRequired):
        manager.retire(version)
    assert not version.retired
    assert not version.closed
    version.core.stop.assert_not_awaited()
    version.core.memory_runtime.aclose.assert_not_awaited()
    await manager.close_all(force=True)
    assert version.closed
    version.core.stop.assert_awaited_once_with(force=True)


@pytest.mark.asyncio
async def test_unpublished_candidate_uses_force_without_blocking_on_declaration():
    version = candidate()
    version.published = False
    await version.retire()
    version.core.assert_hot_unloadable.assert_not_called()
    version.core.stop.assert_awaited_once_with(force=True)


@pytest.mark.asyncio
async def test_retention_drains_accepted_work_without_disposing_its_resources():
    version = candidate()
    accepted = version.acquire()
    retained = RuntimeRetention((version,))
    await version.retire()
    draining = asyncio.create_task(retained.drain())
    await asyncio.sleep(0)
    version.core.drain.assert_not_awaited()
    await accepted.release()
    await asyncio.wait_for(draining, 1)
    version.core.drain.assert_awaited_once()
    version.core.stop.assert_not_awaited()
    assert not version.drained.is_set()
    await retained.release()
    await retained.release()
    version.core.stop.assert_awaited_once()
    assert version.drained.is_set()


@pytest.mark.asyncio
async def test_retention_waits_for_core_work_in_generation_already_closing():
    version = candidate()
    entered, finish = asyncio.Event(), asyncio.Event()

    async def close(**_):
        entered.set()
        await finish.wait()

    version.core.stop.side_effect = close
    closing = asyncio.create_task(version.retire())
    await entered.wait()
    retained = RuntimeRetention((version,))
    draining = asyncio.create_task(retained.drain())
    await asyncio.sleep(0)
    assert not draining.done()
    finish.set()
    await asyncio.wait_for(asyncio.gather(closing, draining), 1)
    await retained.release()
    version.core.stop.assert_awaited_once()


@pytest.mark.asyncio
async def test_retention_observes_scheduled_retirement_without_reacquiring_it():
    from bootstrap.runtime.generations import GenerationManager

    version = candidate()
    manager = GenerationManager()
    manager.start(version)
    manager.retire(version)
    try:
        retained = RuntimeRetention(manager.tracked)
        await asyncio.wait_for(retained.drain(), 1)
        await retained.release()
        version.core.stop.assert_awaited_once()
    finally:
        await manager.close_all(force=True)
