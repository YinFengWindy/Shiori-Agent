import asyncio
from concurrent.futures import Future
from threading import Thread
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from plugins.qq.backend.channel.sdk_runtime import QQSdkRuntime


@pytest.mark.asyncio
async def test_stop_closes_receive_loop_before_sdk_plugin_shutdown():
    connected = asyncio.Event()
    disconnected = asyncio.Event()

    async def receive():
        connected.set()
        try:
            await asyncio.Event().wait()
        finally:
            disconnected.set()

    def bot_exit():
        assert disconnected.is_set()

    bot = SimpleNamespace(
        adapter=SimpleNamespace(connect_websocket=receive),
        bot_exit=Mock(side_effect=bot_exit),
    )
    runtime = QQSdkRuntime(bot)
    task = asyncio.create_task(bot.adapter.connect_websocket())
    await connected.wait()
    await asyncio.wait_for(runtime.stop(), timeout=1)
    assert await task is False
    bot.bot_exit.assert_called_once()


@pytest.mark.asyncio
async def test_stop_before_connection_start_still_unloads_sdk():
    async def receive():
        raise AssertionError("must not connect")

    bot = SimpleNamespace(
        adapter=SimpleNamespace(connect_websocket=receive), bot_exit=Mock()
    )
    runtime = QQSdkRuntime(bot)
    await runtime.stop()
    bot.bot_exit.assert_called_once()


@pytest.mark.asyncio
async def test_stop_waits_for_receive_loop_running_on_sdk_thread():
    connected: Future[None] = Future()
    closed = []

    async def receive():
        connected.set_result(None)
        try:
            await asyncio.Event().wait()
        finally:
            closed.append("socket")

    bot = SimpleNamespace(
        adapter=SimpleNamespace(connect_websocket=receive),
        bot_exit=Mock(side_effect=lambda: closed.append("plugins")),
    )
    runtime = QQSdkRuntime(bot)
    thread = Thread(
        target=lambda: asyncio.run(bot.adapter.connect_websocket()), daemon=True
    )
    thread.start()
    await asyncio.wait_for(asyncio.wrap_future(connected), timeout=1)
    await asyncio.wait_for(runtime.stop(), timeout=1)
    await asyncio.to_thread(thread.join, 1)
    assert not thread.is_alive()
    assert closed == ["socket", "plugins"]
