"""Long-connection runner threading, reconnects, shutdown and the SDK seam."""

from __future__ import annotations

import asyncio
import json
import threading
import warnings
from typing import Any

import pytest

from plugins.feishu.backend import ws
from plugins.feishu.backend.ws import (
    ConnectionState,
    LongConnectionRunner,
    SdkLongConnection,
)


def _feishu_threads() -> list[threading.Thread]:
    return [t for t in threading.enumerate() if t.name.startswith("feishu-ws")]


async def _wait_for(predicate: Any, timeout: float = 5.0) -> None:
    for _ in range(int(timeout / 0.01)):
        if predicate():
            return
        await asyncio.sleep(0.01)
    raise AssertionError("condition not reached")


async def test_runner_connects_on_its_own_thread_and_loop(make_harness: Any) -> None:
    received: list[dict[str, Any]] = []
    host_loop = asyncio.get_running_loop()
    factory = make_harness().factory
    runner = LongConnectionRunner(factory, received.append, name="feishu-ws-test")

    runner.start()
    connection = await factory.wait_connected()

    assert connection.thread_name == "feishu-ws-test"
    assert connection.loop is not host_loop
    assert runner.state == ConnectionState(True, "长连接已建立")
    connection.emit({"header": {"event_id": "e1"}, "event": {}})
    assert received == [{"header": {"event_id": "e1"}, "event": {}}]
    await runner.stop()
    assert not runner.alive
    assert connection.loop.is_closed()
    assert connection.disconnects == 1


async def test_handler_errors_are_contained_so_the_frame_is_still_acked(
    make_harness: Any,
) -> None:
    def explode(_envelope: dict[str, Any]) -> None:
        raise ValueError("boom")

    factory = make_harness().factory
    runner = LongConnectionRunner(factory, explode)
    runner.start()
    connection = await factory.wait_connected()

    connection.emit({"event": {}})  # would raise into the SDK without the guard

    await runner.stop()


async def test_runner_reconnects_after_failures_and_drops(make_harness: Any) -> None:
    factory = make_harness(fail_first=2).factory
    states: list[ConnectionState] = []
    runner = LongConnectionRunner(
        factory,
        lambda _e: None,
        on_state=states.append,
        reconnect_delays=(0.01,),
        poll_interval=0.01,
    )
    runner.start()
    first = await factory.wait_connected()

    assert len(factory.connections) == 3
    assert any(s.detail == "连接失败：fake connect failure" for s in states)
    first.drop()
    await _wait_for(lambda: len(factory.connections) == 4)
    second = await factory.wait_connected()
    assert second is not first
    assert any(s.detail == "连接断开，正在重连" for s in states)
    await runner.stop()


async def test_stop_is_idempotent_and_leaves_no_thread(make_harness: Any) -> None:
    before = len(_feishu_threads())
    factory = make_harness().factory
    runner = LongConnectionRunner(factory, lambda _e: None)
    runner.start()
    await factory.wait_connected()

    await asyncio.wait_for(runner.stop(), 5)
    await asyncio.wait_for(runner.stop(), 5)

    assert len(_feishu_threads()) == before
    assert runner.state == ConnectionState(False, "已停止")


async def test_stop_before_start_and_single_use(make_harness: Any) -> None:
    factory = make_harness().factory
    runner = LongConnectionRunner(factory, lambda _e: None)

    await runner.stop()

    with pytest.raises(RuntimeError):
        runner.start()
    assert factory.connections == []


async def test_stop_during_reconnect_backoff_returns_promptly(
    make_harness: Any,
) -> None:
    factory = make_harness(fail_first=100).factory
    runner = LongConnectionRunner(factory, lambda _e: None, reconnect_delays=(60.0,))
    runner.start()
    await _wait_for(lambda: len(factory.connections) == 1)

    await asyncio.wait_for(runner.stop(), 5)

    assert not runner.alive


async def test_sdk_private_surface_used_by_the_adapter_still_exists() -> None:
    """Tripwire for lark-oapi upgrades: the adapter relies on these internals.

    Async on purpose: the SDK module grabs ``asyncio.get_event_loop()`` on
    import, which outside a running loop would create a loop nobody closes.
    """
    with warnings.catch_warnings():
        # The SDK's vendored protobuf calls datetime.utcfromtimestamp().
        warnings.simplefilter("ignore", DeprecationWarning)
        from lark_oapi.ws import client as client_module

    assert hasattr(client_module, "loop")
    for name in ("_connect", "_disconnect", "_ping_loop", "_handle_data_frame"):
        assert callable(getattr(client_module.Client, name))


async def test_sdk_adapter_rebinds_the_module_loop_and_dispatches_raw_events() -> None:
    """Builds the real SDK client on a private loop and feeds it an event
    payload through the dispatcher, without any network access."""
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", DeprecationWarning)
        from lark_oapi.ws import client as client_module

    received: list[dict[str, Any]] = []
    outcome: dict[str, Any] = {}
    payload = {
        "schema": "2.0",
        "header": {"event_id": "ev-1", "event_type": "im.message.receive_v1"},
        "event": {"message": {"message_id": "om_1", "chat_type": "p2p"}},
    }
    read_payload = dict(payload, header={"event_type": "im.message.message_read_v1"})

    def run() -> None:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)

        async def build() -> None:
            adapter = SdkLongConnection(
                "cli_app", "secret", "https://open.feishu.cn", received.append
            )
            outcome["loop_bound"] = client_module.loop is asyncio.get_running_loop()
            outcome["connected"] = adapter.is_connected()
            handler = adapter._client._event_handler
            handler._do_without_validation(json.dumps(payload).encode())
            handler._do_without_validation(json.dumps(read_payload).encode())

        try:
            loop.run_until_complete(build())
        finally:
            ws._close_loop(loop)
            asyncio.set_event_loop(None)

    thread = threading.Thread(target=run)
    thread.start()
    await asyncio.to_thread(thread.join, 10)

    assert outcome == {"loop_bound": True, "connected": False}
    assert received == [
        {
            "header": {"event_id": "ev-1", "event_type": "im.message.receive_v1"},
            "event": payload["event"],
        }
    ]
