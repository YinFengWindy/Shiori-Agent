import asyncio
from unittest.mock import AsyncMock

import pytest

from agent.config_models import Config
from bootstrap.app import AppRuntime, RuntimeFeatures
from bus.events import SpawnCompletionItem
from core.common.runtime_scope import bind_runtime
from shiori_sdk.messages import OutboundMessage


async def start_app(tmp_path, monkeypatch):
    monkeypatch.setattr("bootstrap.tools._resolve_plugin_dirs", lambda _: [])
    config = Config(
        provider="",
        model="",
        api_key="",
        model_registrations=[],
        memory_optimizer_enabled=False,
    )
    app = AppRuntime(
        config,
        tmp_path,
        features=RuntimeFeatures(enable_message_channels=False, enable_proactive=False),
    )
    await app.start()
    return app


@pytest.mark.asyncio
async def test_shutdown_keeps_http_resources_until_queued_event_lease_drains(
    tmp_path, monkeypatch
):
    app = await start_app(tmp_path, monkeypatch)
    entered, finish = asyncio.Event(), asyncio.Event()

    async def observe(_):
        entered.set()
        await finish.wait()

    app.core.event_bus.on(str, observe)
    lease = app.acquire()
    with bind_runtime(lease):
        app.core.event_bus.enqueue("pending")
    await lease.release()
    await entered.wait()
    shutdown = asyncio.create_task(app.shutdown())
    await asyncio.sleep(0)
    assert not app.http_resources._closed
    assert not shutdown.done()
    finish.set()
    await asyncio.wait_for(shutdown, timeout=2)
    assert app.http_resources._closed
    assert app._generation_manager.current.drained.is_set()


@pytest.mark.asyncio
async def test_shutdown_releases_queued_spawn_completion_lease(tmp_path, monkeypatch):
    app = await start_app(tmp_path, monkeypatch)
    # Keep the completion queued rather than racing the live consumer; this
    # regression exercises ownership release for work that never starts.
    consumer = next(
        task for task in app._background_tasks if task.get_name() == "agent_loop"
    )
    consumer.cancel()
    await asyncio.gather(consumer, return_exceptions=True)
    retained = app.acquire()
    await app.bus.publish_inbound(
        SpawnCompletionItem("desktop", "one", object(), runtime_lease=retained)
    )
    await asyncio.wait_for(app.shutdown(), timeout=2)
    assert app._generation_manager.current.references == 0
    assert app._generation_manager.current.drained.is_set()


@pytest.mark.asyncio
@pytest.mark.parametrize("retained_event", [False, True])
async def test_shutdown_delivers_final_event_reply_before_stopping_live_scope(
    runtime_channels, retained_event
):
    app = await runtime_channels.start()
    entered, finish = asyncio.Event(), asyncio.Event()

    async def reply(_):
        entered.set()
        await finish.wait()
        await app.bus.publish_outbound(OutboundMessage("lifecycle", "one", "last"))

    app.core.event_bus.on(str, reply)
    lease = app.acquire() if retained_event else None
    with bind_runtime(lease):
        app.core.event_bus.enqueue("reply")
    if lease is not None:
        await lease.release()
    await entered.wait()
    shutdown = asyncio.create_task(app.shutdown())
    try:
        await asyncio.sleep(0)
        assert not runtime_channels.channels[0].stopped
        assert not shutdown.done()
    finally:
        finish.set()
        await asyncio.wait_for(shutdown, 3)
    assert runtime_channels.events == ["last", "stop"]
    assert app.http_resources._closed


@pytest.mark.asyncio
async def test_shutdown_propagates_channel_failure_after_closing_other_resources(
    runtime_channels,
):
    app = await runtime_channels.start()
    runtime_channels.fail_stop = True
    with pytest.raises(ExceptionGroup) as caught:
        await asyncio.wait_for(app.shutdown(), 3)
    assert (
        caught.value.subgroup(lambda error: str(error) == "connection cleanup failed")
        is not None
    )
    assert app.http_resources._closed
    assert app.core.event_bus._closed
    assert app._generation_manager.current.drained.is_set()
    assert runtime_channels.channels[0].stop_calls == 1


@pytest.mark.asyncio
async def test_partial_start_stops_channel_before_disposing_plugin(
    runtime_channels, monkeypatch
):
    def fail_background(*_):
        raise RuntimeError("background startup failed")

    monkeypatch.setattr(AppRuntime, "_prepare_background", fail_background)
    with pytest.raises(RuntimeError, match="background startup failed"):
        await runtime_channels.start()
    assert runtime_channels.events == ["stop"]
    assert runtime_channels.app.http_resources._closed


@pytest.mark.asyncio
async def test_failed_work_drain_still_stops_channel_and_disposes_scopes(
    runtime_channels, monkeypatch
):
    app = await runtime_channels.start()
    fail = AsyncMock(side_effect=RuntimeError("maintenance failed"))
    monkeypatch.setattr(app.core.memory_runtime.markdown.maintenance, "drain", fail)
    with pytest.raises(ExceptionGroup) as caught:
        await asyncio.wait_for(app.shutdown(), 3)
    assert (
        caught.value.subgroup(lambda error: str(error) == "maintenance failed")
        is not None
    )
    fail.assert_awaited_once()
    assert runtime_channels.events == ["stop"]
    assert app.core.plugin_manager.loaded_count == 0
    assert app.core.event_bus._closed
    assert app.http_resources._closed


@pytest.mark.asyncio
async def test_shutdown_preserves_drain_channel_and_retirement_errors(
    runtime_channels, monkeypatch
):
    app = await runtime_channels.start()
    drain_error = ValueError("maintenance drain failed")
    retired_error = OSError("prior retired connection failed")
    fail_drain = AsyncMock(side_effect=drain_error)
    monkeypatch.setattr(
        app.core.memory_runtime.markdown.maintenance, "drain", fail_drain
    )
    app.channel_host._retirements.spawn(
        AsyncMock(side_effect=retired_error)(), name="failed-retirement"
    )
    await app.channel_host._retirements.drain()
    runtime_channels.fail_stop = True
    with pytest.raises(ExceptionGroup) as caught:
        await asyncio.wait_for(app.shutdown(), 3)
    for expected in (drain_error, retired_error):
        assert caught.value.subgroup(lambda error: error is expected) is not None
    assert (
        caught.value.subgroup(lambda error: str(error) == "connection cleanup failed")
        is not None
    )
    fail_drain.assert_awaited_once()
    assert runtime_channels.channels[0].stop_calls == 1
    assert app._generation_manager.current.references == 0
    assert app.core.plugin_manager.loaded_count == 0
    assert app.core.event_bus._closed
    assert app.http_resources._closed


@pytest.mark.asyncio
async def test_cancelled_shutdown_waiter_does_not_abandon_live_channel_resources(
    runtime_channels,
):
    app = await runtime_channels.start()
    entered, finish = asyncio.Event(), asyncio.Event()

    async def observe(_):
        entered.set()
        await finish.wait()

    app.core.event_bus.on(str, observe)
    app.core.event_bus.enqueue("pending")
    await entered.wait()
    shutdown = asyncio.create_task(app.shutdown())
    await asyncio.sleep(0)
    shutdown.cancel()
    with pytest.raises(asyncio.CancelledError):
        await shutdown
    finish.set()
    await asyncio.wait_for(app.shutdown(), 3)
    assert runtime_channels.events == ["stop"]
    assert app._generation_manager.current.references == 0
    assert app.http_resources._closed
