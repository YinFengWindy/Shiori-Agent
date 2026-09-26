from __future__ import annotations

import asyncio
import json

import pytest

from plugins.qq.backend.onebot import OneBotDisconnected, OneBotError, OneBotSocket


class _WebSocket:
    def __init__(self) -> None:
        self.sent = []
        self.incoming = asyncio.Queue()
        self.closed = False

    async def send(self, raw):
        self.sent.append(json.loads(raw))

    async def close(self):
        self.closed = True
        await self.incoming.put(None)

    def __aiter__(self):
        return self

    async def __anext__(self):
        raw = await self.incoming.get()
        if raw is None:
            raise StopAsyncIteration
        return raw


@pytest.mark.asyncio
async def test_onebot_correlates_action_replies_and_delivers_events(monkeypatch):
    ws = _WebSocket()
    options = {}

    async def connect(uri, **kwargs):
        options.update(uri=uri, **kwargs)
        return ws

    monkeypatch.setattr("plugins.qq.backend.onebot.connect", connect)
    events = []

    async def on_event(event):
        events.append(event)

    socket = OneBotSocket("ws://localhost:3001", "secret", 3, on_event)
    await socket.open()
    first = asyncio.create_task(socket.call("get_friend_list"))
    second = asyncio.create_task(socket.call("get_group_list"))
    await asyncio.sleep(0)
    assert options == {
        "uri": "ws://localhost:3001",
        "additional_headers": {"Authorization": "Bearer secret"},
        "open_timeout": 3,
    }
    assert len(ws.sent) == 2
    await ws.incoming.put(
        json.dumps(
            {
                "echo": ws.sent[1]["echo"],
                "status": "ok",
                "retcode": 0,
                "data": [{"group_id": 2}],
            }
        )
    )
    await ws.incoming.put(
        json.dumps(
            {
                "post_type": "message",
                "message_type": "private",
                "user_id": 9,
            }
        )
    )
    await ws.incoming.put(
        json.dumps(
            {
                "echo": ws.sent[0]["echo"],
                "status": "failed",
                "retcode": 1404,
                "wording": "not logged in",
            }
        )
    )
    assert await second == [{"group_id": 2}]
    with pytest.raises(OneBotError, match="not logged in"):
        await first
    assert events == [
        {
            "post_type": "message",
            "message_type": "private",
            "user_id": 9,
        }
    ]
    await socket.close()


@pytest.mark.asyncio
async def test_in_flight_action_disconnect_has_uncertain_receipt(monkeypatch):
    ws = _WebSocket()

    async def connect(_uri, **_kwargs):
        return ws

    monkeypatch.setattr("plugins.qq.backend.onebot.connect", connect)
    socket = OneBotSocket("ws://localhost:3001", "", 1, lambda _event: asyncio.sleep(0))
    await socket.open()
    send = asyncio.create_task(
        socket.call("send_private_msg", {"user_id": 9, "message": "hello"})
    )
    await asyncio.sleep(0)
    assert ws.sent[0]["action"] == "send_private_msg"
    await ws.incoming.put(None)

    with pytest.raises(OneBotDisconnected, match="已断开"):
        await send
    await socket.wait_closed()


@pytest.mark.asyncio
async def test_event_notice_can_receive_action_reply_on_the_same_socket(monkeypatch):
    ws = _WebSocket()

    async def connect(_uri, **_kwargs):
        return ws

    async def send_with_reply(raw):
        request = json.loads(raw)
        ws.sent.append(request)
        await ws.incoming.put(
            json.dumps(
                {
                    "echo": request["echo"],
                    "status": "ok",
                    "retcode": 0,
                    "data": {"message_id": 101},
                }
            )
        )

    ws.send = send_with_reply
    monkeypatch.setattr("plugins.qq.backend.onebot.connect", connect)
    delivered = asyncio.Event()
    socket: OneBotSocket | None = None

    async def on_event(_event):
        # ChannelIntake's overflow/retry notice follows this same call path.
        assert socket is not None
        assert await socket.call(
            "send_private_msg", {"user_id": 9, "message": "retry"}
        ) == {"message_id": 101}
        delivered.set()

    socket = OneBotSocket("ws://localhost:3001", "", 1, on_event)
    await socket.open()
    await ws.incoming.put(json.dumps({"post_type": "message", "user_id": 9}))
    await asyncio.wait_for(delivered.wait(), timeout=1)
    assert ws.sent[0]["action"] == "send_private_msg"
    await socket.close()


@pytest.mark.asyncio
async def test_reader_closes_transport_on_invalid_json(monkeypatch):
    ws = _WebSocket()

    async def connect(_uri, **_kwargs):
        return ws

    monkeypatch.setattr("plugins.qq.backend.onebot.connect", connect)
    socket = OneBotSocket("ws://localhost:3001", "", 1, lambda _event: asyncio.sleep(0))
    await socket.open()
    await ws.incoming.put("{")
    with pytest.raises(json.JSONDecodeError):
        await socket.wait_closed()
    assert ws.closed


@pytest.mark.asyncio
async def test_event_queue_overflow_closes_socket_without_unbounded_workers(
    monkeypatch,
):
    ws = _WebSocket()

    async def connect(_uri, **_kwargs):
        return ws

    monkeypatch.setattr("plugins.qq.backend.onebot.connect", connect)
    entered = asyncio.Event()
    blocked = asyncio.Event()

    async def on_event(_event):
        entered.set()
        await blocked.wait()

    socket = OneBotSocket("ws://localhost:3001", "", 1, on_event)
    socket._events = asyncio.Queue(maxsize=1)
    await socket.open()
    event = json.dumps({"post_type": "message"})
    await ws.incoming.put(event)
    await asyncio.wait_for(entered.wait(), timeout=1)
    await ws.incoming.put(event)
    await ws.incoming.put(event)
    with pytest.raises(OneBotError, match="队列已满"):
        await socket.wait_closed()
    assert ws.closed
    assert socket._event_worker.done()
