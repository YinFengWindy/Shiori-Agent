from __future__ import annotations

import base64
import json
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock

import httpx
import pytest

from shiori_sdk.channels.services import CHANNEL_INTAKE_RETRY_NOTICE
from shiori_sdk.messages import InboundMessage, OutboundMessage
from shiori_sdk.testing.channel_context import (
    FakeChannelDeclarations,
    fake_channel_context,
)
from shiori_sdk.testing.channel_hub import FakeChannelHub
from shiori_sdk.testing.channel_services import (
    FakeInterruptController,
    FakeMessageBus,
    FakePushSenders,
)
from shiori_sdk.testing.events import FakeEvents
import plugins.qqbot.backend.channel as qqbot_channel
from plugins.qqbot.backend.channel import QQBotChannel


async def _started(
    tmp_path: Path,
    *args: Any,
    bus: FakeMessageBus | None = None,
    hub: FakeChannelHub | None = None,
    interrupt_controller: FakeInterruptController | None = None,
    **kwargs: Any,
) -> QQBotChannel:
    """A channel started through the host's public start context, without a gateway."""
    channel = QQBotChannel(*args, **kwargs)

    async def _no_gateway_loop() -> None:
        return None

    channel._gateway_loop = _no_gateway_loop
    await channel.start(
        fake_channel_context(
            tmp_path,
            bus=bus,
            channel_hub=hub,
            interrupt_controller=interrupt_controller,
        )
    )
    return channel


def _receipts(hub: FakeChannelHub) -> list[tuple[object, object]]:
    return [(item["delivery_status"], item["chat_id"]) for item in hub.deliveries]


@pytest.mark.asyncio
async def test_qqbot_channel_registers_and_stops_cleanly(tmp_path: Path) -> None:
    bus = FakeMessageBus()
    push_tool = FakePushSenders()
    events = FakeEvents()
    channel = QQBotChannel("app", "secret")

    async def _no_gateway_loop() -> None:
        return None

    channel._gateway_loop = _no_gateway_loop
    assert channel._client is None
    await channel.start(
        fake_channel_context(tmp_path, bus=bus, push_tool=push_tool, event_bus=events)
    )
    client = channel._client
    assert client is not None and not client.is_closed
    assert list(bus.outbound) == ["qqbot"]
    assert sorted(push_tool.registrations["qqbot"]) == [
        "description",
        "image",
        "stream_text",
        "text",
    ]
    await channel.stop()
    assert client.is_closed
    assert channel._client is None

    assert bus.outbound == {}
    assert events._subscriptions == []
    assert push_tool.registrations == {}


@pytest.mark.asyncio
async def test_qqbot_pauses_intake_until_removal_is_rolled_back(tmp_path: Path):
    bus = FakeMessageBus()
    channel = await _started(tmp_path, "app", "secret", bus=bus)
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
    assert bus.inbound == []
    channel.resume_intake()
    await channel._intake.drain()
    assert [item.content for item in bus.inbound] == ["buffered"]
    await channel.stop()


@pytest.mark.asyncio
async def test_qqbot_reports_pending_input_before_closing_original_account(
    monkeypatch, tmp_path: Path
):
    notices = []

    async def send(self, chat_id, text):
        assert self._client is client and not client.is_closed
        notices.append((self._app_id, chat_id, text))

    monkeypatch.setattr(QQBotChannel, "send", send)
    channel = QQBotChannel("old-account", "secret")
    client = httpx.AsyncClient(
        transport=httpx.MockTransport(lambda _request: httpx.Response(200))
    )
    channel._client = client

    async def _no_gateway_loop() -> None:
        return None

    channel._gateway_loop = _no_gateway_loop
    bus = FakeMessageBus()
    await channel.start(fake_channel_context(tmp_path, bus=bus))
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
    assert bus.inbound == []
    assert notices == [
        ("old-account", "c2c:old-account:user", CHANNEL_INTAKE_RETRY_NOTICE)
    ]
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
    await QQBotChannel(
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
async def test_qqbot_c2c_inbound_is_role_routed_and_deduplicated(
    tmp_path: Path,
) -> None:
    bus = FakeMessageBus()
    channel = await _started(tmp_path, "app", "secret", bus=bus)
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
    await channel.stop()


@pytest.mark.asyncio
async def test_c2c_inbound_is_scoped_to_its_application_account(
    tmp_path: Path,
) -> None:
    bus = FakeMessageBus()
    via = {
        "platform": "qqbot",
        "platform_account_id": "app-1",
        "display_name": "Bot",
        "prefix": "QQ 机器人「Bot」（AppID app-1）",
    }
    channel = await _started(
        tmp_path,
        "app-1",
        "secret",
        bus=bus,
        account_id="account-1",
        via_account=lambda: via,
    )
    channel._send_input_notify = AsyncMock()

    await channel._handle_c2c(
        {"id": "message-1", "author": {"user_openid": "opaque-user"}, "content": "hi"}
    )

    assert bus.inbound[0].chat_id == "c2c:app-1:opaque-user"
    assert bus.inbound[0].metadata["account_id"] == "account-1"
    assert bus.inbound[0].metadata["qqbot_app_id"] == "app-1"
    assert bus.inbound[0].metadata["via_account"] == via
    await channel.stop()


@pytest.mark.asyncio
async def test_qqbot_c2c_inbound_requires_role_binding(tmp_path: Path) -> None:
    bus = FakeMessageBus()
    channel = await _started(
        tmp_path, "app", "secret", bus=bus, hub=FakeChannelHub(allowed=False)
    )
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
    await channel.stop()


@pytest.mark.asyncio
async def test_qqbot_send_uses_official_markdown_api() -> None:
    channel = QQBotChannel("app", "secret")
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
    channel = QQBotChannel("app", "secret")
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
    channel = QQBotChannel("app", "secret")
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
    channel = QQBotChannel("app", "secret")
    channel._get_access_token = AsyncMock(return_value="access-token")
    channel._api_request = AsyncMock()

    with pytest.raises(ValueError, match="仅支持 PNG、JPEG、WebP 和 GIF"):
        await channel.send_image("c2c:app:user-1", str(image))

    channel._get_access_token.assert_not_awaited()
    channel._api_request.assert_not_awaited()


@pytest.mark.asyncio
async def test_qqbot_send_image_requires_file_info_from_upload() -> None:
    channel = QQBotChannel("app", "secret")
    channel._get_access_token = AsyncMock(return_value="access-token")
    channel._api_request = AsyncMock(return_value={})

    with pytest.raises(RuntimeError, match="缺少 file_info"):
        await channel.send_image("c2c:app:user-1", "https://example.com/image.png")

    channel._api_request.assert_awaited_once()


@pytest.mark.asyncio
async def test_qqbot_response_records_delivery_for_role_thread(tmp_path: Path) -> None:
    hub = FakeChannelHub()
    channel = await _started(tmp_path, "app", "secret", hub=hub)
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
    assert _receipts(hub) == [("sent", "c2c:app:user-1")]
    await channel.stop()


@pytest.mark.asyncio
async def test_qqbot_response_sends_media_and_records_delivery_after_success(
    tmp_path: Path,
) -> None:
    hub = FakeChannelHub()
    channel = await _started(tmp_path, "app", "secret", hub=hub)
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
    assert _receipts(hub) == [("sent", "c2c:app:user-1")]
    await channel.stop()


@pytest.mark.asyncio
async def test_qqbot_response_marks_media_failure_without_sent_status(
    tmp_path: Path,
) -> None:
    hub = FakeChannelHub()
    channel = await _started(tmp_path, "app", "secret", hub=hub)
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

    assert _receipts(hub) == [("failed", "c2c:app:user-1")]
    await channel.stop()


@pytest.mark.asyncio
async def test_qqbot_stop_uses_bound_role_session(tmp_path: Path) -> None:
    interrupt = FakeInterruptController(message="已中断")
    channel = await _started(tmp_path, "app", "secret", interrupt_controller=interrupt)
    channel.send = AsyncMock()

    await channel._handle_stop("c2c:app:user-1", "user-1")

    assert interrupt.requests == [
        {"session_key": "role:mira", "sender": "user-1", "command": "/stop"}
    ]
    channel.send.assert_awaited_once_with("c2c:app:user-1", "已中断")
    await channel.stop()


@pytest.mark.asyncio
async def test_qqbot_stop_from_unadmitted_sender_is_ignored(tmp_path: Path) -> None:
    interrupt = FakeInterruptController()
    channel = await _started(
        tmp_path,
        "app",
        "secret",
        hub=FakeChannelHub(allowed=False),
        interrupt_controller=interrupt,
    )
    channel.send = AsyncMock()

    await channel._handle_stop("c2c:app:user-1", "user-1")

    assert interrupt.requests == []
    channel.send.assert_not_awaited()
    await channel.stop()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("hub", "replies"),
    [
        # Unbound chats are answered: that is how the OpenID to bind is found.
        (
            FakeChannelHub(allowed=False),
            [("c2c:app:user-1", "会话类型：私聊\n用户 OpenID：user-1")],
        ),
        (
            FakeChannelHub(),
            [("c2c:app:user-1", "会话类型：私聊\n用户 OpenID：user-1")],
        ),
        (FakeChannelHub(allowed=False, blocked=True), []),
    ],
    ids=["unbound", "bound", "blacklisted"],
)
async def test_qqbot_chatid_answers_without_entering_the_role(
    tmp_path: Path, hub: FakeChannelHub, replies: list[tuple[str, str]]
) -> None:
    manifest = FakeChannelDeclarations(
        Path(qqbot_channel.__file__).resolve().parents[1]
    )
    bus = FakeMessageBus()
    channel = await _started(
        tmp_path,
        "app",
        "secret",
        bus=bus,
        hub=hub,
        chat_types=manifest.channel_chat_types("qqbot"),
    )
    channel._send_input_notify = AsyncMock()
    channel.send = AsyncMock()

    await channel._handle_c2c(
        {"id": "message-1", "author": {"user_openid": "user-1"}, "content": "/chatid"}
    )

    assert [call.args for call in channel.send.await_args_list] == replies
    assert bus.inbound == []
    channel._send_input_notify.assert_not_awaited()
    assert channel._last_c2c_msg_id == {}
    await channel.stop()


@pytest.mark.asyncio
async def test_qqbot_push_senders_return_the_platform_message_id() -> None:
    channel = QQBotChannel("app", "secret")
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
    channel = QQBotChannel("app", "secret")
    channel._get_access_token = AsyncMock(return_value="access-token")
    channel._api_request = AsyncMock(return_value={"id": "plain-id"})

    # No inbound message to anchor a stream: sent as a plain message.
    assert await channel.send_stream("c2c:app:user-1", "回复") == "plain-id"


@pytest.mark.asyncio
async def test_qqbot_pairing_code_binds_with_app_scope_without_entering_the_role(
    tmp_path: Path,
) -> None:
    bus = FakeMessageBus()
    hub = FakeChannelHub(pairing_code="PAIR1234")
    channel = await _started(
        tmp_path, "app-1", "secret", bus=bus, hub=hub, account_id="account-1"
    )
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
    await channel.stop()
