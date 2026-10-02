from __future__ import annotations

from shiori_sdk.testing.channel_intake import FakeChannelIntake as ChannelIntake
import base64
import json
import logging
from pathlib import Path
from types import SimpleNamespace
from typing import Any, cast
from unittest.mock import AsyncMock, MagicMock

import httpx
import pytest

from shiori_sdk.testing.events import FakeEvents as EventBus
from shiori_sdk.messages import InboundMessage, OutboundMessage
from shiori_sdk.channels import ChannelContext
import plugins.qqbot.backend.channel as qqbot_channel
from plugins.qqbot.backend.channel import QQBotChannel


def _channel(*args, **kwargs) -> QQBotChannel:
    channel = QQBotChannel(*args, **kwargs)
    channel._intake = ChannelIntake(channel._accept_inbound, channel.send)
    return channel


class _Bus:
    def __init__(self) -> None:
        self.inbound: list[InboundMessage] = []
        self.outbound: list[tuple[str, object]] = []

    async def publish_inbound(self, message: InboundMessage) -> None:
        self.inbound.append(message)

    def subscribe_outbound(self, channel: str, callback: object) -> None:
        self.outbound.append((channel, callback))

    def unsubscribe_outbound(self, channel: str, callback: object) -> None:
        self.outbound = [item for item in self.outbound if item != (channel, callback)]


class _PushTool:
    def __init__(self) -> None:
        self.registrations: list[tuple[str, list[str]]] = []
        self.removed: list[str] = []

    def register_channel(self, name: str, **kwargs: object) -> None:
        self.registrations.append((name, sorted(kwargs)))

    def unregister_channel(self, name: str, **kwargs: object) -> None:
        self.removed.append(name)


class _Hub:
    def __init__(self, *, allowed: bool = True, blocked: bool = False) -> None:
        self.allowed = allowed
        self.blocked = blocked
        self.deliveries: list[tuple[str, str]] = []

    def is_sender_allowed(self, **kwargs: object) -> bool:
        return self.allowed

    def is_sender_blocked(self, **kwargs: object) -> bool:
        return self.blocked

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
        intake_factory=ChannelIntake,
        bus=cast(Any, bus),
        session_manager=cast(Any, SimpleNamespace()),
        event_bus=EventBus(),
        push_tool=cast(Any, push_tool),
        attachment_store=MagicMock(),
        http_resources=cast(Any, SimpleNamespace()),
        interrupt_controller=None,
        bot_commands=[],
        log=logging.getLogger("test.qqbot"),
        channel_hub=cast(Any, hub),
    )


@pytest.mark.asyncio
async def test_qqbot_channel_registers_and_stops_cleanly(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    bus = _Bus()
    push_tool = _PushTool()
    channel = _channel("app", "secret")

    async def _no_gateway_loop() -> None:
        return None

    channel._gateway_loop = _no_gateway_loop
    context = _context(bus, push_tool, _Hub())
    assert channel._client is None
    await channel.start(context)
    client = channel._client
    assert client is not None and not client.is_closed
    assert bus.outbound[0][0] == "qqbot"
    await channel.stop()
    assert client.is_closed
    assert channel._client is None

    assert bus.outbound == []
    assert context.event_bus._subscriptions == []
    assert push_tool.removed == ["qqbot"]
    assert push_tool.registrations == [
        ("qqbot", ["description", "image", "stream_text", "text"])
    ]


@pytest.mark.asyncio
async def test_qqbot_pauses_intake_until_removal_is_rolled_back():
    channel = _channel("app", "secret")
    channel._bus = _Bus()
    channel._send_input_notify = AsyncMock()
    channel.pause_intake()
    await channel._handle_dispatch(
        "C2C_MESSAGE_CREATE",
        {
            "id": "1",
            "author": {"user_openid": "user"},
            "content": "buffered",
        },
    )
    assert channel._bus.inbound == []
    channel.resume_intake()
    await channel._intake.drain()
    assert [item.content for item in channel._bus.inbound] == ["buffered"]
    await channel.stop()


@pytest.mark.asyncio
async def test_qqbot_reports_pending_input_before_closing_original_account(monkeypatch):
    notices = []

    async def send(self, chat_id, text):
        assert self._client is client and not client.is_closed
        notices.append((self._app_id, chat_id, text))

    monkeypatch.setattr(QQBotChannel, "send", send)
    channel = _channel("old-account", "secret")
    client = httpx.AsyncClient(
        transport=httpx.MockTransport(lambda _request: httpx.Response(200))
    )
    channel._client = client
    channel._bus = _Bus()
    channel.pause_intake()
    await channel._publish_inbound(
        InboundMessage(
            channel="qqbot",
            sender="user",
            chat_id="c2c:old-account:user",
            content="pending",
        )
    )
    await channel.stop()
    assert channel._bus.inbound == []
    assert len(notices) == 1
    assert notices[0][:2] == ("old-account", "c2c:old-account:user")
    assert "重新发送" in notices[0][2]
    assert client.is_closed
    assert channel._client is None


@pytest.mark.asyncio
async def test_qqbot_gateway_sends_identify_payload(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class _WebSocket:
        def __init__(self) -> None:
            self.sent: list[dict[str, Any]] = []
            self._messages = iter(
                [
                    json.dumps({"op": 10, "d": {"heartbeat_interval": 60_000}}),
                    json.dumps(
                        {
                            "op": 0,
                            "t": "READY",
                            "d": {"user": {"id": "bot-id", "username": "Bot One"}},
                        }
                    ),
                    json.dumps({"op": 7, "d": {}}),
                ]
            )

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

    statuses: list[tuple[str, str, str, str]] = []
    await _channel(
        "app", "secret", on_status=lambda *status: statuses.append(status)
    )._run_gateway("wss://gateway.invalid", "token")

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
    assert statuses == [("online", "", "Bot One", "bot-id")]


@pytest.mark.asyncio
async def test_qqbot_c2c_inbound_is_role_routed_and_deduplicated() -> None:
    bus = _Bus()
    channel = _channel("app", "secret")
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
    assert bus.inbound[0].chat_id == "c2c:app:user-1"
    assert bus.inbound[0].metadata["role_id"] == "mira"
    assert channel._send_input_notify.await_count == 2


@pytest.mark.asyncio
async def test_c2c_inbound_is_scoped_to_its_application_account() -> None:
    bus = _Bus()
    via = {
        "platform": "qqbot",
        "platform_account_id": "app-1",
        "display_name": "Bot",
        "prefix": "QQ 机器人「Bot」（AppID app-1）",
    }
    channel = _channel(
        "app-1", "secret", account_id="account-1", via_account=lambda: via
    )
    channel._bus = bus
    channel._channel_hub = _Hub()
    channel._send_input_notify = AsyncMock()

    await channel._handle_c2c(
        {"id": "message-1", "author": {"user_openid": "opaque-user"}, "content": "hi"}
    )

    assert bus.inbound[0].chat_id == "c2c:app-1:opaque-user"
    assert bus.inbound[0].metadata["account_id"] == "account-1"
    assert bus.inbound[0].metadata["qqbot_app_id"] == "app-1"
    assert bus.inbound[0].metadata["via_account"] == via


@pytest.mark.asyncio
async def test_qqbot_c2c_inbound_requires_role_binding() -> None:
    bus = _Bus()
    channel = _channel("app", "secret")
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
    # No side effect for a rejected sender: no input notify, no reply anchor.
    channel._send_input_notify.assert_not_awaited()
    assert channel._last_c2c_msg_id == {}


@pytest.mark.asyncio
async def test_qqbot_send_uses_official_markdown_api() -> None:
    channel = _channel("app", "secret")
    channel._get_access_token = AsyncMock(return_value="access-token")
    channel._api_request = AsyncMock(return_value={})

    await channel.send("c2c:app:user-1", "回复")

    channel._api_request.assert_awaited_once()
    call = channel._api_request.await_args
    assert call.args[:3] == (
        "POST",
        "/v2/users/user-1/messages",
        {
            "markdown": {"content": "回复"},
            "msg_type": 2,
            "msg_seq": call.args[2]["msg_seq"],
        },
    )
    assert call.args[3] == "access-token"


@pytest.mark.asyncio
async def test_qqbot_send_image_uploads_public_url_then_sends_media() -> None:
    channel = _channel("app", "secret")
    channel._get_access_token = AsyncMock(return_value="access-token")
    channel._api_request = AsyncMock(side_effect=[{"file_info": "uploaded-file"}, {}])

    await channel.send_image("c2c:app:user-1", "https://example.com/sticker.gif")

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
    channel = _channel("app", "secret")
    channel._get_access_token = AsyncMock(return_value="access-token")
    channel._api_request = AsyncMock(side_effect=[{"file_info": "gif-file"}, {}])

    await channel.send_image("c2c:app:user-1", str(image))

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
    channel = _channel("app", "secret")
    channel._get_access_token = AsyncMock(return_value="access-token")
    channel._api_request = AsyncMock()

    with pytest.raises(ValueError, match="仅支持 PNG、JPEG、WebP 和 GIF"):
        await channel.send_image("c2c:app:user-1", str(image))

    channel._get_access_token.assert_not_awaited()
    channel._api_request.assert_not_awaited()


@pytest.mark.asyncio
async def test_qqbot_send_image_requires_file_info_from_upload() -> None:
    channel = _channel("app", "secret")
    channel._get_access_token = AsyncMock(return_value="access-token")
    channel._api_request = AsyncMock(return_value={})

    with pytest.raises(RuntimeError, match="缺少 file_info"):
        await channel.send_image("c2c:app:user-1", "https://example.com/image.png")

    channel._api_request.assert_awaited_once()


@pytest.mark.asyncio
async def test_qqbot_response_records_delivery_for_role_thread() -> None:
    hub = _Hub()
    channel = _channel("app", "secret")
    channel._channel_hub = hub
    channel.send = AsyncMock()

    await channel._on_response(
        OutboundMessage(
            channel="qqbot",
            chat_id="c2c:app:user-1",
            content="回复",
            metadata={
                "role_id": "mira",
                "thread_id": "thread:mira:qqbot:c2c:app:user-1",
                "session_key_override": "role:mira",
            },
        )
    )

    channel.send.assert_awaited_once_with("c2c:app:user-1", "回复")
    assert hub.deliveries == [("sent", "c2c:app:user-1")]


@pytest.mark.asyncio
async def test_qqbot_response_sends_media_and_records_delivery_after_success() -> None:
    hub = _Hub()
    channel = _channel("app", "secret")
    channel._channel_hub = hub
    channel.send = AsyncMock()
    channel.send_image = AsyncMock()

    await channel._on_response(
        OutboundMessage(
            channel="qqbot",
            chat_id="c2c:app:user-1",
            content="",
            media=["first.png", "second.png"],
        )
    )

    channel.send.assert_not_awaited()
    assert channel.send_image.await_args_list == [
        (("c2c:app:user-1", "first.png"),),
        (("c2c:app:user-1", "second.png"),),
    ]
    assert hub.deliveries == [("sent", "c2c:app:user-1")]


@pytest.mark.asyncio
async def test_qqbot_response_marks_media_failure_without_sent_status() -> None:
    hub = _Hub()
    channel = _channel("app", "secret")
    channel._channel_hub = hub
    channel.send_image = AsyncMock(side_effect=RuntimeError("upload failed"))

    with pytest.raises(RuntimeError, match="upload failed"):
        await channel._on_response(
            OutboundMessage(
                channel="qqbot",
                chat_id="c2c:app:user-1",
                content="",
                media=["broken.png"],
            )
        )

    assert hub.deliveries == [("failed", "c2c:app:user-1")]


@pytest.mark.asyncio
async def test_qqbot_stop_uses_bound_role_session() -> None:
    hub = _Hub()
    interrupt = SimpleNamespace(
        request_interrupt=MagicMock(return_value=SimpleNamespace(message="已中断"))
    )
    channel = _channel("app", "secret")
    channel._channel_hub = hub
    channel._interrupt_controller = interrupt
    channel.send = AsyncMock()

    await channel._handle_stop("c2c:app:user-1", "user-1")

    interrupt.request_interrupt.assert_called_once_with(
        session_key="role:mira",
        sender="user-1",
        command="/stop",
    )
    channel.send.assert_awaited_once_with("c2c:app:user-1", "已中断")


@pytest.mark.asyncio
async def test_qqbot_stop_from_unadmitted_sender_is_ignored() -> None:
    interrupt = SimpleNamespace(request_interrupt=MagicMock())
    channel = _channel("app", "secret")
    channel._channel_hub = _Hub(allowed=False)
    channel._interrupt_controller = interrupt
    channel.send = AsyncMock()

    await channel._handle_stop("c2c:app:user-1", "user-1")

    interrupt.request_interrupt.assert_not_called()
    channel.send.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("hub", "replies"),
    [
        # Unbound chats are answered: that is how the OpenID to bind is found.
        (
            _Hub(allowed=False),
            [("c2c:app:user-1", "会话类型：私聊\n用户 OpenID：user-1")],
        ),
        (_Hub(), [("c2c:app:user-1", "会话类型：私聊\n用户 OpenID：user-1")]),
        (_Hub(allowed=False, blocked=True), []),
    ],
    ids=["unbound", "bound", "blacklisted"],
)
async def test_qqbot_chatid_answers_without_entering_the_role(
    hub: _Hub, replies: list[tuple[str, str]]
) -> None:
    from shiori_sdk.testing.channel_context import FakeChannelDeclarations

    manifest = FakeChannelDeclarations(
        Path(qqbot_channel.__file__).resolve().parents[1]
    )
    assert manifest is not None
    bus = _Bus()
    channel = _channel("app", "secret", chat_types=manifest.channel_chat_types("qqbot"))
    channel._bus = bus
    channel._channel_hub = hub
    channel._send_input_notify = AsyncMock()
    channel.send = AsyncMock()

    await channel._handle_c2c(
        {"id": "message-1", "author": {"user_openid": "user-1"}, "content": "/chatid"}
    )

    assert [call.args for call in channel.send.await_args_list] == replies
    assert bus.inbound == []
    channel._send_input_notify.assert_not_awaited()
    assert channel._last_c2c_msg_id == {}


@pytest.mark.asyncio
async def test_qqbot_push_senders_return_the_platform_message_id() -> None:
    channel = _channel("app", "secret")
    channel._get_access_token = AsyncMock(return_value="access-token")
    channel._api_request = AsyncMock(
        side_effect=[
            {"id": "text-id"},
            {"file_info": "uploaded-file"},
            {"id": "image-id"},
            {"id": "stream-id"},
            {},
        ]
    )
    channel._last_c2c_msg_id["user-1"] = "inbound-1"

    assert await channel.send_proactive("c2c:app:user-1", "回复") == "text-id"
    assert (
        await channel.send_image("c2c:app:user-1", "https://example.com/a.png")
        == "image-id"
    )
    # The first stream chunk assigns the id; later chunks reuse it.
    assert await channel.send_stream("c2c:app:user-1", "x" * 200) == "stream-id"


@pytest.mark.asyncio
async def test_qqbot_stream_fallback_returns_the_plain_message_id() -> None:
    channel = _channel("app", "secret")
    channel._get_access_token = AsyncMock(return_value="access-token")
    channel._api_request = AsyncMock(return_value={"id": "plain-id"})

    # No inbound message to anchor a stream: sent as a plain message.
    assert await channel.send_stream("c2c:app:user-1", "回复") == "plain-id"


class _PairingHub(_Hub):
    """An account-routing hub whose pending pairing code is ``PAIR1234``."""

    def __init__(self) -> None:
        super().__init__()
        self.pairings: list[tuple[str, str, str]] = []

    def route_account_inbound(self, message: InboundMessage) -> InboundMessage:
        return self.route_inbound(message)

    def claim_pairing(self, message: InboundMessage, *, scope: str) -> bool:
        self.pairings.append((message.sender, message.content, scope))
        return message.content == "PAIR1234"


@pytest.mark.asyncio
async def test_qqbot_pairing_code_binds_with_app_scope_without_entering_the_role() -> (
    None
):
    bus = _Bus()
    hub = _PairingHub()
    channel = _channel("app-1", "secret", account_id="account-1")
    channel._bus = bus
    channel._channel_hub = hub
    channel._send_input_notify = AsyncMock()
    channel.send = AsyncMock()

    for message_id, content in (("m1", "PAIR1234"), ("m2", "你好")):
        await channel._handle_c2c(
            {"id": message_id, "author": {"user_openid": "user-1"}, "content": content}
        )

    assert hub.pairings == [
        ("user-1", "PAIR1234", "account"),
        ("user-1", "你好", "account"),
    ]
    channel.send.assert_awaited_once_with("c2c:app-1:user-1", "已绑定")
    assert [message.content for message in bus.inbound] == ["你好"]
