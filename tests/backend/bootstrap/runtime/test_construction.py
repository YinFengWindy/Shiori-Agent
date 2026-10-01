from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from bootstrap.runtime.construction import prepare_core_runtime, track_build_resource


@pytest.mark.asyncio
async def test_construction_failure_closes_partial_resources_once_in_reverse_order():
    closed = []
    first, second = object(), object()

    def build():
        track_build_resource(first, lambda: closed.append("first"))
        track_build_resource(second, lambda: closed.append("second"))
        track_build_resource(first, lambda: closed.append("duplicate"))
        raise ValueError("invalid memory config")

    with pytest.raises(ValueError, match="invalid memory config"):
        await prepare_core_runtime(builder=build)
    assert closed == ["second", "first"]


@pytest.mark.asyncio
async def test_complete_runtime_takes_ownership_without_closing_resources():
    resource = SimpleNamespace(aclose=AsyncMock())

    def build():
        track_build_resource(resource, resource.aclose)
        return SimpleNamespace(provider=resource)

    runtime = await prepare_core_runtime(builder=build)
    assert runtime.provider is resource
    resource.aclose.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize("failure_after_transfer", [False, True])
async def test_memory_build_callbacks_close_partial_or_transferred_resources_once(
    failure_after_transfer,
):
    from bootstrap.runtime.construction import MemoryBuildResources

    closed = []

    def build():
        resources = MemoryBuildResources()
        resources.register(object(), lambda: closed.append("first"))
        resources.register(object(), lambda: closed.append("second"))
        if failure_after_transfer:
            transferred = resources.transfer()
            assert len(transferred) == 2
        raise ValueError("assembly failed")

    with pytest.raises(ValueError, match="assembly failed"):
        await prepare_core_runtime(builder=build)
    assert closed == ["second", "first"]


@pytest.mark.asyncio
async def test_successful_memory_handoff_uses_explicit_cleanup_callbacks():
    from bootstrap.runtime.construction import MemoryBuildResources
    from core.memory.plugin import DisabledMemoryEngine
    from core.memory.runtime import MemoryRuntime

    closed = []

    def build():
        resources = MemoryBuildResources()
        resources.register(object(), lambda: closed.append("opaque-resource"))
        return MemoryRuntime(
            markdown=SimpleNamespace(),
            engine=DisabledMemoryEngine(),
            resources=resources.transfer(),
        )

    runtime = await prepare_core_runtime(builder=build)
    assert closed == []
    await runtime.aclose()
    await runtime.aclose()
    assert closed == ["opaque-resource"]
