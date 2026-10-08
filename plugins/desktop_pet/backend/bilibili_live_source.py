"""The real logged-in Bilibili danmaku stream connection.

Connection flow (bilibili-API-collect ``docs/live/message_stream.md``,
blivedm ``clients/ws_base.py``): fetch a fresh token and hosts, open
``wss://host:port/sub``, send the auth packet within 5 s, expect auth reply
``{"code": 0}``, then send a heartbeat every 30 s (the server drops silent
clients after about 60 s) while reading command packets. The reader and the
heartbeat live and die together: the first one to fail ends the connection
with its own error. Reconnecting is the caller's job.
"""

from __future__ import annotations

import asyncio
from contextlib import AbstractAsyncContextManager

from websockets.asyncio.client import connect

from .bilibili_api import BILIBILI_HEADERS
from .bilibili_credentials import BilibiliCredentials
from .bilibili_danmaku import AnonymousDanmaku, DanmakuFormatError, parse_danmaku
from .bilibili_live_api import BilibiliLiveApi
from .bilibili_live_packets import (
    AUTH_PROTOVER,
    OP_AUTH,
    OP_HEARTBEAT,
    AuthReply,
    decode_frame,
    encode_packet,
)
from .bilibili_live_stream import (
    DanmakuSink,
    LiveAuthRejected,
    LiveDisconnected,
    LiveIdentityRejected,
    LiveSocket,
    SocketConnector,
)

HEARTBEAT_INTERVAL_S = 30.0
# Heartbeat replies arrive every 30 s, so a longer silence is a dead link.
RECEIVE_TIMEOUT_S = 45.0
_MAX_FRAME_BYTES = 4 * 1024 * 1024


def open_websocket(url: str) -> AbstractAsyncContextManager[LiveSocket]:
    """Default connector; keepalive is the protocol heartbeat, not ws pings."""
    return connect(
        url,
        additional_headers={"User-Agent": BILIBILI_HEADERS["User-Agent"]},
        ping_interval=None,
        max_size=_MAX_FRAME_BYTES,
    )


class BilibiliDanmakuSource:
    """The real stream: logged-in auth packet, heartbeat and command decoding."""

    def __init__(
        self,
        api: BilibiliLiveApi,
        connector: SocketConnector = open_websocket,
        *,
        heartbeat_s: float = HEARTBEAT_INTERVAL_S,
        receive_timeout_s: float = RECEIVE_TIMEOUT_S,
    ) -> None:
        self._api = api
        self._connector = connector
        self._heartbeat_s = heartbeat_s
        self._receive_timeout_s = receive_timeout_s

    async def run(
        self,
        room_id: int,
        credentials: BilibiliCredentials,
        buvid: str,
        sink: DanmakuSink,
    ) -> None:
        """Connect to the first host of a fresh endpoint and stream from it."""
        cookies = {**credentials.cookies, "buvid3": buvid}
        endpoint = await self._api.fetch_endpoint(room_id, cookies)
        auth = {
            "uid": credentials.uid,
            "roomid": room_id,
            "protover": AUTH_PROTOVER,
            "buvid": buvid,
            "platform": "web",
            "type": 2,
            "key": endpoint.token,
        }
        async with self._connector(endpoint.urls[0]) as socket:
            await socket.send(encode_packet(OP_AUTH, auth))
            reader = asyncio.ensure_future(self._read(socket, sink))
            heartbeat = asyncio.ensure_future(self._heartbeat(socket))
            try:
                await asyncio.wait(
                    (reader, heartbeat), return_when=asyncio.FIRST_EXCEPTION
                )
            finally:
                reader.cancel()
                heartbeat.cancel()
                await asyncio.gather(reader, heartbeat, return_exceptions=True)
            # Both loops only end by raising; the reader's error is reported first.
            (heartbeat if reader.cancelled() else reader).result()

    async def _heartbeat(self, socket: LiveSocket) -> None:
        while True:
            await socket.send(encode_packet(OP_HEARTBEAT, {}))
            await asyncio.sleep(self._heartbeat_s)

    async def _read(self, socket: LiveSocket, sink: DanmakuSink) -> None:
        while True:
            try:
                async with asyncio.timeout(self._receive_timeout_s):
                    frame = await socket.recv()
            except TimeoutError as error:
                raise LiveDisconnected("弹幕连接长时间无数据") from error
            if not isinstance(frame, bytes):
                continue
            for item in decode_frame(frame):
                if isinstance(item, AuthReply):
                    if item.code != 0:
                        raise LiveAuthRejected(f"弹幕服务器拒绝认证 code={item.code}")
                    sink.connected()
                    continue
                try:
                    message = parse_danmaku(item.body)
                except AnonymousDanmaku as error:
                    raise LiveIdentityRejected(str(error)) from error
                except DanmakuFormatError as error:
                    sink.unreadable(str(error))
                    continue
                if message is not None:
                    sink.danmaku(message)
