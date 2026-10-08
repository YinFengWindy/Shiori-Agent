"""Reconnect backoff is bounded and resets after a successful connection."""

import asyncio

from plugins.desktop_pet.backend.bilibili_credentials import BilibiliCredentials
from plugins.desktop_pet.backend.bilibili_live_api import LiveRoom
from plugins.desktop_pet.backend.live_connection import LiveConnection, reconnect_delay
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


async def test_failed_attempts_back_off_and_a_connection_resets(clock, danmaku_source):
    async def credentials():
        return CREDENTIALS

    status = LiveStatus("mira", LiveRoom(1001, "t"))
    connection = LiveConnection(
        room_id=1001,
        buvid="b",
        credentials=credentials,
        source=danmaku_source,
        on_danmaku=lambda message: None,
        status=status,
        clock=clock,
    )
    danmaku_source.authenticate = False
    task = asyncio.create_task(connection.run())
    await clock.settle()

    async def fail_and_wait(delay: float) -> None:
        count = len(danmaku_source.connections)
        danmaku_source.current.drop(ConnectionError("reset"))
        await clock.advance(delay - 0.01)
        assert len(danmaku_source.connections) == count
        await clock.advance(0.01)
        assert len(danmaku_source.connections) == count + 1

    await fail_and_wait(1)
    await fail_and_wait(2)
    assert status.connection == "reconnecting"
    assert status.last_error == "弹幕连接中断: reset"
    danmaku_source.authenticate = True
    await fail_and_wait(4)
    assert status.connection == "connected"
    await fail_and_wait(1)
    task.cancel()
    await asyncio.gather(task, return_exceptions=True)
