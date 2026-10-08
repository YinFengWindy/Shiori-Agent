"""The real source over a scripted socket: logged-in auth, heartbeat, decoding, failures."""

import asyncio
import json
import struct
import zlib
from contextlib import asynccontextmanager

import pytest

from plugins.desktop_pet.backend.bilibili_credentials import BilibiliCredentials
from plugins.desktop_pet.backend.bilibili_danmaku import Danmaku
from plugins.desktop_pet.backend.bilibili_live_api import BilibiliLiveApi
from plugins.desktop_pet.backend.bilibili_live_source import BilibiliDanmakuSource
from plugins.desktop_pet.backend.bilibili_live_stream import (
    LiveAuthRejected,
    LiveDisconnected,
    LiveIdentityRejected,
)

CREDENTIALS = BilibiliCredentials(
    uid=42,
    uname="主播",
    cookies={"SESSDATA": "sess%2C1%2Cabc", "bili_jct": "jct", "DedeUserID": "42"},
    refresh_token="r",
)


def packet(operation: int, version: int, body: bytes) -> bytes:
    return struct.pack(">IHHII", 16 + len(body), 16, version, operation, 0) + body


def danmu(message_id: str, uid: int = 7) -> bytes:
    meta = [0, 1, 25, 0, 1, 2, 0, "h", 0, 0, 0, "", 0, "{}", "{}"]
    meta.append({"extra": json.dumps({"id_str": message_id})})
    body = {"cmd": "DANMU_MSG", "info": [meta, "你好", [uid, "小明"]]}
    return packet(5, 0, json.dumps(body).encode("utf-8"))


class ScriptedSocket:
    def __init__(self, frames: list[bytes], send_error: Exception | None = None):
        self.frames = frames
        self.sent: list[bytes] = []
        self.send_error = send_error

    async def send(self, message: bytes) -> None:
        if self.sent and self.send_error is not None:
            raise self.send_error
        self.sent.append(message)

    async def recv(self) -> bytes:
        if not self.frames:
            await asyncio.Event().wait()
        return self.frames.pop(0)


class Sink:
    def __init__(self) -> None:
        self.events: list[object] = []

    def connected(self) -> None:
        self.events.append("connected")

    def danmaku(self, message: Danmaku) -> None:
        self.events.append(message.message_id)

    def unreadable(self, error: str) -> None:
        self.events.append("unreadable")


def source_for(bilibili, socket: ScriptedSocket, urls: list[str]):
    @asynccontextmanager
    async def connector(url: str):
        urls.append(url)
        yield socket

    api = BilibiliLiveApi(bilibili.transport)
    return BilibiliDanmakuSource(api, connector, heartbeat_s=60, receive_timeout_s=0.05)


async def test_logged_in_stream_authenticates_and_delivers_danmaku(bilibili):
    batch = zlib.compress(danmu("a") + danmu("b"))
    socket = ScriptedSocket(
        [
            packet(8, 1, b'{"code":0}'),
            packet(5, 2, batch),
            packet(5, 0, b'{"cmd":"DANMU_MSG","info":[]}'),
        ]
    )
    urls: list[str] = []
    sink = Sink()
    with pytest.raises(LiveDisconnected):
        await source_for(bilibili, socket, urls).run(1001, CREDENTIALS, "BUVID", sink)

    assert urls == ["wss://comet.example:443/sub"]
    auth = json.loads(socket.sent[0][16:])
    assert auth == {
        "uid": 42,
        "roomid": 1001,
        "protover": 2,
        "buvid": "BUVID",
        "platform": "web",
        "type": 2,
        "key": "stream-token",
    }
    assert struct.unpack(">IHHII", socket.sent[1][:16])[3] == 2, "heartbeat sent"
    assert sink.events == ["connected", "a", "b", "unreadable"]


async def test_rejected_auth_and_anonymized_senders_are_distinct_failures(bilibili):
    rejected = ScriptedSocket([packet(8, 1, b'{"code":-101}')])
    with pytest.raises(LiveAuthRejected):
        await source_for(bilibili, rejected, []).run(1001, CREDENTIALS, "B", Sink())
    anonymous = ScriptedSocket([packet(8, 1, b'{"code":0}'), danmu("a", uid=0)])
    with pytest.raises(LiveIdentityRejected):
        await source_for(bilibili, anonymous, []).run(1001, CREDENTIALS, "B", Sink())


async def test_failed_heartbeat_ends_the_connection_with_its_own_error(bilibili):
    socket = ScriptedSocket([packet(8, 1, b'{"code":0}')], OSError("broken pipe"))
    sink = Sink()
    source = source_for(bilibili, socket, [])
    with pytest.raises(OSError, match="broken pipe"):
        await asyncio.wait_for(source.run(1001, CREDENTIALS, "B", sink), 1)
    assert sink.events == ["connected"]
