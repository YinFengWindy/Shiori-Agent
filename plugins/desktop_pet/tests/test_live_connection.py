"""Reconnects: transient failures back off (bounded), rejections and bugs do not retry."""

import asyncio

import pytest

from plugins.desktop_pet.backend.bilibili_credentials import BilibiliCredentials
from plugins.desktop_pet.backend.bilibili_live_api import LiveRoom
from plugins.desktop_pet.backend.bilibili_live_packets import LivePacketError
from plugins.desktop_pet.backend.bilibili_live_stream import LiveAuthRejected
from plugins.desktop_pet.backend.live_connection import (
    LiveConnection,
    LiveConnectionEnded,
    reconnect_delay,
)
from plugins.desktop_pet.backend.live_status import LiveStatus

CREDENTIALS = BilibiliCredentials(
    uid=42, uname="主播", cookies={"SESSDATA": "s"}, refresh_token="r"
)


def test_backoff_doubles_up_to_the_cap():
    assert [reconnect_delay(n) for n in (1, 2, 3, 4, 5, 6, 7, 20)] == [
        1,
        2,
        4,
        8,
        16,
        30,
        30,
        30,
    ]


async def start(clock, source) -> tuple[LiveConnection, LiveStatus, asyncio.Task]:
    async def credentials():
        return CREDENTIALS

    status = LiveStatus("mira", LiveRoom(1001, "t"))
    connection = LiveConnection(
        room_id=1001,
        buvid="b",
        credentials=credentials,
        source=source,
        on_danmaku=lambda message: None,
        status=status,
        clock=clock,
    )
    task = asyncio.create_task(connection.run())
    await clock.settle()
    return connection, status, task


async def fail_and_wait(clock, source, delay: float) -> None:
    count = len(source.connections)
    source.current.drop(ConnectionError("reset"))
    await clock.advance(delay - 0.01)
    assert len(source.connections) == count
    await clock.advance(0.01)
    assert len(source.connections) == count + 1


async def test_quick_drops_keep_backing_off_and_only_a_healthy_link_resets(
    clock, danmaku_source
):
    _, status, task = await start(clock, danmaku_source)
    assert status.connection == "connected"
    # Each connection authenticates and then drops at once: no reset.
    await fail_and_wait(clock, danmaku_source, 1)
    await fail_and_wait(clock, danmaku_source, 2)
    await fail_and_wait(clock, danmaku_source, 4)
    await clock.advance(30)
    await fail_and_wait(clock, danmaku_source, 1)
    task.cancel()
    await asyncio.gather(task, return_exceptions=True)


async def test_rejection_ends_without_retrying(clock, danmaku_source):
    _, status, task = await start(clock, danmaku_source)
    danmaku_source.current.drop(LiveAuthRejected("拒绝"))
    with pytest.raises(LiveConnectionEnded) as ended:
        await task
    assert ended.value.state == "rejected"
    assert (status.connection, status.connection_error) == ("rejected", "拒绝")
    await clock.advance(60)
    assert len(danmaku_source.connections) == 1


async def test_protocol_errors_propagate_instead_of_reconnecting(clock, danmaku_source):
    _, _, task = await start(clock, danmaku_source)
    danmaku_source.current.drop(LivePacketError("坏包"))
    with pytest.raises(LivePacketError):
        await task
    await clock.advance(60)
    assert len(danmaku_source.connections) == 1
