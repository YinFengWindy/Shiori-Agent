import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest

from bootstrap.runtime.background import RuntimeBackground
from bootstrap.runtime.generations import RuntimeCandidate
from core.common.runtime_scope import current_runtime_lease


class WorkLoop:
    def __init__(self):
        self.started = asyncio.Event()
        self.finish = asyncio.Event()
        self.stopped = False
        self.cancelled = False
        self.version = None

    async def run(self):
        self.version = current_runtime_lease().generation
        self.started.set()
        try:
            await self.finish.wait()
        except asyncio.CancelledError:
            self.cancelled = True
            raise

    def stop(self):
        self.stopped = True


def candidate(number):
    core = SimpleNamespace(
        provider=None,
        role_runtime_registry=None,
        stop=AsyncMock(),
        assert_hot_unloadable=Mock(),
        memory_runtime=SimpleNamespace(
            markdown=SimpleNamespace(store=None), aclose=AsyncMock()
        ),
    )
    return RuntimeCandidate(
        number, core, SimpleNamespace(model_registrations=[]), published=True
    )


def _install_loops(monkeypatch, *loops):
    remaining = iter(loops)

    def build(*args, loop_consumer, **kwargs):
        loop = next(remaining)
        loop_consumer(loop)
        return [loop.run()], None

    monkeypatch.setattr(
        "bootstrap.runtime.background.build_memory_optimizer_task", build
    )


@pytest.mark.asyncio
async def test_stop_cancels_in_flight_work_before_next_generation_starts(monkeypatch):
    # The old loop ignores stop(), like an optimizer stuck in a retried model call.
    old_loop, new_loop = WorkLoop(), WorkLoop()
    _install_loops(monkeypatch, old_loop, new_loop)
    app = SimpleNamespace(features=SimpleNamespace(enable_proactive=False))
    old_version, new_version = candidate(1), candidate(2)
    old_group = RuntimeBackground(app, old_version)
    new_group = RuntimeBackground(app, new_version)
    old_group.start()
    await old_loop.started.wait()
    old_group.stop()
    await old_version.retire()
    new_group.start(old_group)
    await asyncio.wait_for(new_loop.started.wait(), timeout=1)
    assert old_loop.stopped and old_loop.cancelled
    assert (old_loop.version, new_loop.version) == (1, 2)
    assert old_version.drained.is_set()
    new_group.stop()
    await asyncio.wait_for(new_group.drain(), timeout=1)
    await new_version.retire()


@pytest.mark.asyncio
async def test_drain_reports_failures_raised_while_work_unwinds(monkeypatch):
    class FailingCleanup(WorkLoop):
        async def run(self):
            try:
                await super().run()
            finally:
                raise OSError("cleanup failed")

    loop = FailingCleanup()
    _install_loops(monkeypatch, loop)
    version = candidate(1)
    group = RuntimeBackground(
        SimpleNamespace(features=SimpleNamespace(enable_proactive=False)), version
    )
    group.start()
    await loop.started.wait()
    group.stop()
    with pytest.raises(BaseExceptionGroup) as failure:
        await asyncio.wait_for(group.drain(), timeout=1)
    assert [str(error) for error in failure.value.exceptions] == ["cleanup failed"]
    await version.retire()


def test_scene_intake_activates_at_publication_even_without_polling_loops(monkeypatch):
    from unittest.mock import Mock

    monkeypatch.setattr(
        "bootstrap.runtime.background.build_memory_optimizer_task",
        lambda *args, **kwargs: ([], None),
    )
    version = candidate(1)
    scene = SimpleNamespace(activate=Mock(), deactivate=Mock())
    version.core.scene_service = scene
    group = RuntimeBackground(
        SimpleNamespace(features=SimpleNamespace(enable_proactive=False)), version
    )
    scene.activate.assert_not_called()
    group.start()
    scene.activate.assert_called_once()
    group.stop()
    # Accepted old turns still emit their AfterTurn on this generation-local bus.
    scene.deactivate.assert_not_called()
