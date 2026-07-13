from __future__ import annotations

import base64
import json
import logging
from pathlib import Path
from types import SimpleNamespace
from typing import Any, cast
from unittest.mock import AsyncMock, MagicMock

import pytest

from bus.event_bus import EventBus
from bus.events import InboundMessage, OutboundMessage
from infra.channels.base import AttachmentStore
from infra.channels.contract import ChannelContext
import plugins.qqbot.channel as qqbot_channel
from plugins.qqbot.channel import QQBotChannel


class _Bus:
    def __init__(self) -> None:
        self.inbound: list[InboundMessage] = []
        self.outbound: list[tuple[str, object]] = []

    async def publish_inbound(self, message: InboundMessage) -> None:
        self.inbound.append(message)

    def subscribe_outbound(self, channel: str, callback: object) -> None:
        self.outbound.append((channel, callback))


class _PushTool:
    def __init__(self) -> None:
        self.registrations: list[tuple[str, list[str]]] = []

    def register_channel(self, name: str, **kwargs: object) -> None:
        self.registrations.append((name, sorted(kwargs)))


class _Hub:
    def __init__(self, *, allowed: bool = True) -> None:
        self.allowed = allowed
        self.deliveries: list[tuple[str, str]] = []

    def is_sender_allowed(self, **kwargs: object) -> bool:
        return self.allowed

    def route_inbound(self, message: InboundMessage) -> InboundMessage:
        external_message_id = str(message.metadata.get("external_message_id") or "")
        seen_ids = getattr(self, "_seen_ids", set())
        if external_message_id in seen_ids:
            message.metadata["conversation_duplicate"] = True
        seen_ids.add(external_message_id)
        self._seen_ids = seen_ids
        message.metadata["role_id"] = "mira"
        return message

    def resolve_runtime_session_key(self, channel: str, chat_id: str) -> str:
        return "role:mira"

    def mark_delivery(self, message: OutboundMessage, **kwargs: object) -> None:
        self.deliveries.append((str(kwargs["delivery_status"]), message.chat_id))


def _context(bus: _Bus, push_tool: _PushTool, hub: _Hub) -> ChannelContext:
    return ChannelContext(
        bus=cast(Any, bus),
        session_manager=cast(Any, SimpleNamespace()),
        event_bus=EventBus(),
        push_tool=cast(Any, push_tool),
        attachment_store=AttachmentStore(),
        http_resources=cast(Any, SimpleNamespace()),
        interrupt_controller=None,
        bot_commands=[],
        log=logging.getLogger("test.qqbot"),
        channel_hub=cast(Any, hub),
    )


@pytest.mark.asyncio
async def test_qqbot_channel_registers_and_stops_cleanly(monkeypatch: pytest.MonkeyPatch) -> None:
    bus = _Bus()
    push_tool = _PushTool()
    channel = QQBotChannel("app", "secret")

    async def _no_gateway_loop() -> None:
        return None

    channel._gateway_loop = _no_gateway_loop
    await channel.start(_context(bus, push_tool, _Hub()))
    await channel.stop()

    assert bus.outbound[0][0] == "qqbot"
    assert push_tool.registrations == [
        ("qqbot", ["image", "stream_text", "text"])
    ]


@pytest.mark.asyncio
async def test_qqbot_gateway_sends_identify_payload(monkeypatch: pytest.MonkeyPatch) -> None:
    class _WebSocket:
        def __init__(self) -> None:
            self.sent: list[dict[str, Any]] = []
            self._messages = iter([
                json.dumps({"op": 10, "d": {"heartbeat_interval": 60_000}}),
                json.dumps({"op": 7, "d": {}}),
            ])

        async def __aenter__(self):
            return self

        async def __aexit__(self, *_args: object) -> None:
            return None

        def __aiter__(self):
            return self

        async def __anext__(self):
            try:
                return next(self._messages)
            except StopIteration as exc:
                raise StopAsyncIteration from exc

        async def send(self, payload: str) -> None:
            self.sent.append(json.loads(payload))

    websocket = _WebSocket()
    monkeypatch.setattr(qqbot_channel.websockets, "connect", lambda _url: websocket)

    await QQBotChannel("app", "secret")._run_gateway("wss://gateway.invalid", "token")

    assert websocket.sent == [
        {
            "op": 2,
            "d": {
                "token": "QQBot token",
                "intents": 1 << 25,
                "shard": [0, 1],
            },
        }
    ]


@pytest.mark.asyncio
async def test_qqbot_c2c_inbound_is_role_routed_and_deduplicated() -> None:
    bus = _Bus()
    channel = QQBotChannel("app", "secret")
    channel._bus = bus
    channel._channel_hub = _Hub()
    channel._send_input_notify = AsyncMock()

    event = {
        "id": "message-1",
        "author": {"user_openid": "user-1"},
        "content": "你好",
    }
    await channel._handle_c2c(event)
    await channel._handle_c2c(event)

    assert len(bus.inbound) == 1
    assert bus.inbound[0].chat_id == "c2c:user-1"
    assert bus.inbound[0].metadata["role_id"] == "mira"
    assert channel._send_input_notify.await_count == 2


@pytest.mark.asyncio
async def test_qqbot_c2c_inbound_requires_role_binding() -> None:
    bus = _Bus()
    channel = QQBotChannel("app", "secret")
    channel._bus = bus
    channel._channel_hub = _Hub(allowed=False)
    channel._send_input_notify = AsyncMock()

    await channel._handle_c2c(
        {
            "id": "message-1",
            "author": {"user_openid": "user-1"},
            "content": "不应进入角色",
        }
    )

    assert bus.inbound == []


@pytest.mark.asyncio
async def test_qqbot_send_uses_official_markdown_api() -> None:
    channel = QQBotChannel("app", "secret")
    channel._get_access_token = AsyncMock(return_value="access-token")
    channel._api_request = AsyncMock(return_value={})

    await channel.send("c2c:user-1", "回复")

    channel._api_request.assert_awaited_once()
    call = channel._api_request.await_args
    assert call.args[:3] == (
        "POST",
        "/v2/users/user-1/messages",
        {"markdown": {"content": "回复"}, "msg_type": 2, "msg_seq": call.args[2]["msg_seq"]},
    )
    assert call.args[3] == "access-token"


@pytest.mark.asyncio
async def test_qqbot_send_image_uploads_public_url_then_sends_media() -> None:
    channel = QQBotChannel("app", "secret")
    channel._get_access_token = AsyncMock(return_value="access-token")
    channel._api_request = AsyncMock(
        side_effect=[{"file_info": "uploaded-file"}, {}]
    )

    await channel.send_image("c2c:user-1", "https://example.com/sticker.gif")

    upload_call, send_call = channel._api_request.await_args_list
    assert upload_call.args == (
        "POST",
        "/v2/users/user-1/files",
        {
            "file_type": 1,
            "url": "https://example.com/sticker.gif",
            "srv_send_msg": False,
        },
        "access-token",
    )
    assert send_call.args[:3] == (
        "POST",
        "/v2/users/user-1/messages",
        {
            "msg_type": 7,
            "media": {"file_info": "uploaded-file"},
            "msg_seq": send_call.args[2]["msg_seq"],
        },
    )
    assert send_call.args[3] == "access-token"


@pytest.mark.asyncio
async def test_qqbot_send_image_uploads_local_gif_without_converting(
    tmp_path: Path,
) -> None:
    raw = b"GIF89a" + b"animated-sticker-data"
    image = tmp_path / "sticker.gif"
    image.write_bytes(raw)
    channel = QQBotChannel("app", "secret")
    channel._get_access_token = AsyncMock(return_value="access-token")
    channel._api_request = AsyncMock(
        side_effect=[{"file_info": "gif-file"}, {}]
    )

    await channel.send_image("c2c:user-1", str(image))

    upload_body = channel._api_request.await_args_list[0].args[2]
    assert upload_body == {
        "file_type": 1,
        "file_data": base64.b64encode(raw).decode("ascii"),
        "srv_send_msg": False,
    }


@pytest.mark.asyncio
async def test_qqbot_send_image_rejects_unsupported_local_file(
    tmp_path: Path,
) -> None:
    image = tmp_path / "not-an-image.txt"
    image.write_text("not an image", encoding="utf-8")
    channel = QQBotChannel("app", "secret")
    channel._get_access_token = AsyncMock(return_value="access-token")
    channel._api_request = AsyncMock()

    with pytest.raises(ValueError, match="仅支持 PNG、JPEG、WebP 和 GIF"):
        await channel.send_image("c2c:user-1", str(image))

    channel._get_access_token.assert_not_awaited()
    channel._api_request.assert_not_awaited()


@pytest.mark.asyncio
async def test_qqbot_send_image_requires_file_info_from_upload() -> None:
    channel = QQBotChannel("app", "secret")
    channel._get_access_token = AsyncMock(return_value="access-token")
    channel._api_request = AsyncMock(return_value={})

    with pytest.raises(RuntimeError, match="缺少 file_info"):
        await channel.send_image("c2c:user-1", "https://example.com/image.png")

    channel._api_request.assert_awaited_once()


@pytest.mark.asyncio
async def test_qqbot_response_records_delivery_for_role_thread() -> None:
    hub = _Hub()
    channel = QQBotChannel("app", "secret")
    channel._channel_hub = hub
    channel.send = AsyncMock()

    await channel._on_response(
        OutboundMessage(
            channel="qqbot",
            chat_id="c2c:user-1",
            content="回复",
            metadata={
                "role_id": "mira",
                "thread_id": "thread:mira:qqbot:c2c:user-1",
                "session_key_override": "role:mira",
            },
        )
    )

    channel.send.assert_awaited_once_with("c2c:user-1", "回复")
    assert hub.deliveries == [("sent", "c2c:user-1")]


@pytest.mark.asyncio
async def test_qqbot_stop_uses_bound_role_session() -> None:
    hub = _Hub()
    interrupt = SimpleNamespace(
        request_interrupt=MagicMock(return_value=SimpleNamespace(message="已中断"))
    )
    channel = QQBotChannel("app", "secret")
    channel._channel_hub = hub
    channel._interrupt_controller = interrupt
    channel.send = AsyncMock()

    await channel._handle_stop("c2c:user-1", "user-1")

    interrupt.request_interrupt.assert_called_once_with(
        session_key="role:mira",
        sender="user-1",
        command="/stop",
    )
    channel.send.assert_awaited_once_with("c2c:user-1", "已中断")
