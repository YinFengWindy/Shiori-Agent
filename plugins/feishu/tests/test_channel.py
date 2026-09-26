"""Channel lifecycle, delivery, fallbacks and status."""

from __future__ import annotations

import asyncio
import json
import threading
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, Mock

import pytest
import httpx

from bus.events import OutboundMessage
from plugins.feishu.backend import api as feishu_api
from plugins.feishu.backend.channel import FeishuChannel, resolve_receive_id
from agent.plugin_host.kv import PluginKVStore

CHAT_ID = "oc_chat"


@pytest.mark.parametrize(
    ("http_status", "expected"), [(401, "login_required"), (403, "error")]
)
async def test_bot_identity_failure_distinguishes_auth_from_capability(
    make_harness: Any, http_status: int, expected: str
) -> None:
    accounts = Mock()
    harness = make_harness(
        account_id="account-a",
        profile_ref="feishu:cli_a",
        accounts=accounts,
    )
    harness.api.fail("bot", (http_status, 10003 if http_status == 401 else 99991672))
    await harness.start()
    for _ in range(100):
        if any(
            call.kwargs.get("connection") == expected
            for call in accounts.report.call_args_list
        ):
            break
        await asyncio.sleep(0.01)
    assert any(
        call.kwargs.get("connection") == expected
        for call in accounts.report.call_args_list
    )
    assert harness.channel.status()["connected"] is True


async def test_bare_http_401_identity_response_requires_login(
    make_harness: Any,
) -> None:
    accounts = Mock()
    harness = make_harness(
        account_id="account-a",
        profile_ref="feishu:cli_a",
        accounts=accounts,
    )

    async def response(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("tenant_access_token/internal"):
            return httpx.Response(200, json={"code": 0, "tenant_access_token": "token"})
        return httpx.Response(401, json={"code": 0})

    harness.channel._api._transport = httpx.MockTransport(response)
    await harness.start()
    for _ in range(100):
        if any(
            call.kwargs.get("connection") == "login_required"
            for call in accounts.report.call_args_list
        ):
            break
        await asyncio.sleep(0.01)
    assert any(
        call.kwargs.get("connection") == "login_required"
        for call in accounts.report.call_args_list
    )


async def test_two_account_channels_isolate_inbound_targets_and_receipts(
    make_harness: Any, tmp_path: Path, make_event: Any
) -> None:
    first = make_harness(
        name="feishu",
        account_id="account-a",
        profile_ref="feishu:cli_a",
        profile_store=PluginKVStore(tmp_path / "first.json"),
    )
    second = make_harness(
        name="feishu:lark:cli_b",
        account_id="account-b",
        profile_ref="lark:cli_b",
        profile_store=PluginKVStore(tmp_path / "second.json"),
    )
    second.context.bus = first.context.bus
    await first.start()
    await second.start()
    first.factory.connections[-1].emit(
        make_event(message_id="om_a", event_id="event-a")
    )
    other = make_event(message_id="om_b", event_id="event-b")
    other["event"]["sender"]["sender_id"]["open_id"] = "ou_other"
    second.factory.connections[-1].emit(other)
    await first.settle()
    await second.settle()

    by_channel = {message.channel: message for message in first.bus.inbound}
    assert set(by_channel) == {"feishu", "feishu:lark:cli_b"}
    assert by_channel["feishu"].metadata["account_id"] == "account-a"
    assert by_channel["feishu:lark:cli_b"].metadata["account_id"] == "account-b"
    assert first.channel.known_private_targets()[0]["open_id"] == "ou_user"
    assert second.channel.known_private_targets()[0]["open_id"] == "ou_other"
    receipt = await second.channel.send(CHAT_ID, "reply")
    assert receipt in second.api.sent_ids
    assert not first.api.sent_ids
    before = len(second.api.sent_ids)
    with pytest.raises(ValueError, match="已交互的私聊"):
        await second.channel.send("oc_unknown_group", "must not send")
    with pytest.raises(ValueError, match="已交互的私聊"):
        await second.channel.send("ou_unknown", "must not send")
    assert len(second.api.sent_ids) == before


@pytest.mark.parametrize("normal_reply", [False, True])
async def test_chunk_send_keeps_first_nonempty_receipt(
    harness: Any, normal_reply: bool
) -> None:
    from plugins.feishu.backend.formatting import CARD_TEXT_LIMIT

    await harness.start()
    harness.hub.mark_delivery = Mock()
    harness.channel._send_chunk = AsyncMock(side_effect=["", "om_second"])
    content = "甲" * (CARD_TEXT_LIMIT - 10) + "\n" + "乙" * 20
    if normal_reply:
        message = OutboundMessage(
            channel="feishu",
            chat_id=CHAT_ID,
            content=content,
            metadata={"external_message_id": "om_incoming"},
            committed_message_id="committed",
        )
        await harness.channel._on_response(message)
        harness.hub.mark_delivery.assert_called_once_with(
            message,
            default_channel="feishu",
            delivery_status="sent",
            external_message_id="om_second",
        )
    else:
        assert await harness.channel.send(CHAT_ID, content) == "om_second"
    assert harness.channel._send_chunk.await_count == 2


async def test_partial_chunk_failure_retains_first_receipt(harness: Any) -> None:
    from plugins.feishu.backend.formatting import CARD_TEXT_LIMIT

    await harness.start()
    harness.hub.mark_delivery = Mock()
    # The first chunk quotes the inbound message; the second chunk and its
    # existing plain-text fallback both fail on the ordinary send endpoint.
    harness.api.fail("send", (400, 99991672), (400, 99991672))
    message = OutboundMessage(
        channel="feishu",
        chat_id=CHAT_ID,
        content="甲" * (CARD_TEXT_LIMIT - 10) + "\n" + "乙" * 20,
        metadata={"external_message_id": "om_incoming", "message_id": "om_incoming"},
        committed_message_id="committed",
    )
    with pytest.raises(feishu_api.FeishuApiError):
        await harness.channel._on_response(message)
    assert len(harness.api.sent_ids) == 1
    assert len(harness.api.bodies("send")) == 2
    harness.hub.mark_delivery.assert_called_once_with(
        message,
        default_channel="feishu",
        delivery_status="failed",
        external_message_id=harness.api.sent_ids[0],
    )


@pytest.mark.parametrize(
    "mode",
    [
        "text",
        "chunks",
        "image",
        "text_image",
        "stream",
        "stream_chunks",
        "fallback",
        "missing",
        "failed",
        "cancelled",
    ],
)
async def test_response_records_retained_platform_receipt(
    harness: Any, tmp_path: Path, mode: str
) -> None:
    await harness.start()
    hub = harness.hub
    hub.mark_delivery = Mock()
    text = "reply"
    if "chunks" in mode:
        from plugins.feishu.backend.formatting import CARD_TEXT_LIMIT

        text = "甲" * (CARD_TEXT_LIMIT - 10) + "\n" + "乙" * 20
    if mode in {"stream", "stream_chunks", "fallback"}:
        await harness.channel._streamer.begin_turn("role:mira", quote="om_incoming")
        harness.channel._streamer.add_delta("role:mira", CHAT_ID, "preview")
        await harness.channel._streamer.drain()
        if mode == "fallback":
            harness.api.fail("stream_text", (400, 99991672))
    if mode == "missing":
        harness.channel._api.reply_message = AsyncMock(return_value="")
    if mode in {"failed", "cancelled"}:
        failure = (
            asyncio.CancelledError() if mode == "cancelled" else RuntimeError("failed")
        )
        harness.channel._send_text = AsyncMock(side_effect=failure)
    image = tmp_path / "image.png"
    image.write_bytes(b"image")
    message = OutboundMessage(
        channel="feishu",
        chat_id=CHAT_ID,
        content="" if mode == "image" else text,
        media=[str(image), str(image)] if mode in {"image", "text_image"} else [],
        metadata={
            "session_key_override": "role:mira",
            "external_message_id": "om_incoming",
            "message_id": "om_incoming",
        },
        committed_message_id="committed",
    )
    if mode in {"failed", "cancelled"}:
        with pytest.raises(type(failure)):
            await harness.channel._on_response(message)
    else:
        await harness.channel._on_response(message)
    expected = (
        harness.api.sent_ids[1]
        if mode == "fallback"
        else (harness.api.sent_ids[0] if harness.api.sent_ids else "")
    )
    hub.mark_delivery.assert_called_once_with(
        message,
        default_channel="feishu",
        delivery_status="failed" if mode in {"failed", "cancelled"} else "sent",
        external_message_id=expected,
    )
    if mode == "fallback":
        assert any(
            path.endswith(harness.api.sent_ids[0]) and method == "DELETE"
            for method, path, body in harness.api.calls
        )


def _feishu_threads() -> list[threading.Thread]:
    return [t for t in threading.enumerate() if t.name == "feishu-ws"]


async def test_start_registers_hooks_and_stop_releases_everything(
    harness: Any,
) -> None:
    before = len(_feishu_threads())
    await harness.start()

    assert harness.bus.outbound[0][0] == "feishu"
    registered = harness.push_tool.registered["feishu"]
    assert sorted(registered) == ["description", "file", "image", "text"]
    assert "oc_" in str(registered["description"])
    assert len(_feishu_threads()) == before + 1

    await harness.channel.stop()

    assert harness.bus.outbound == []
    assert harness.event_bus._handlers == {}
    assert harness.push_tool.removed == ["feishu"]
    assert harness.channel._api._client is None
    assert len(_feishu_threads()) == before
    assert harness.channel.status()["connected"] is False


async def test_stop_is_idempotent_and_safe_before_start(tmp_path: Path) -> None:
    channel = FeishuChannel("cli_app", "secret", "https://open.feishu.cn")

    await channel.stop()  # a reused generation stops its unused new instance
    await channel.stop()

    assert channel.status() == {"connected": False, "detail": "未启动"}


async def test_stop_twice_after_start(harness: Any) -> None:
    await harness.start()

    await harness.channel.stop()
    await harness.channel.stop()

    assert harness.push_tool.removed == ["feishu"]


async def test_channel_can_restart_after_stop(harness: Any, make_event: Any) -> None:
    await harness.start()
    await harness.channel.stop()

    connection = await harness.start()
    connection.emit(make_event())
    await harness.settle()

    assert len(harness.factory.connections) == 2
    assert [item.content for item in harness.bus.inbound] == ["你好"]


async def test_stop_replies_to_buffered_input_before_disconnecting(
    harness: Any, make_event: Any
) -> None:
    connection = await harness.start()
    harness.channel.pause_intake()
    connection.emit(make_event())
    await harness.settle()

    await harness.channel.stop()

    assert harness.bus.inbound == []
    [notice] = harness.api.sent_texts()
    assert "重新发送" in notice


async def test_events_arriving_after_stop_are_dropped(
    harness: Any, make_event: Any
) -> None:
    connection = await harness.start()
    harness.channel._accepting = False  # the state stop() enters first

    connection.emit(make_event())
    await asyncio.sleep(0.05)

    assert harness.channel._inbound_tasks == set()


async def test_status_reports_connection_and_bot_name(harness: Any) -> None:
    await harness.start()
    for _ in range(100):
        if harness.channel.status().get("account"):
            break
        await asyncio.sleep(0.01)

    assert harness.channel.status() == {
        "connected": True,
        "account": "Shiori",
        "detail": "长连接已建立；机器人 open_id=ou_bot",
    }


async def test_final_reply_without_streaming_is_a_markdown_card(
    harness: Any,
) -> None:
    await harness.start()

    await harness.channel._on_response(
        OutboundMessage(channel="feishu", chat_id=CHAT_ID, content="**你好**")
    )

    [body] = harness.api.bodies("send")
    card = json.loads(body["content"])
    assert body["msg_type"] == "interactive" and card["schema"] == "2.0"
    assert card["body"]["elements"][0] == {"tag": "markdown", "content": "**你好**"}
    assert harness.hub.deliveries == ["sent"]


async def test_reply_to_quotes_the_original_message(harness: Any) -> None:
    await harness.start()

    await harness.channel._on_response(
        OutboundMessage(
            channel="feishu", chat_id=CHAT_ID, content="收到", reply_to="om_user"
        )
    )

    assert [path for _m, path, _b in harness.api.calls][-1] == (
        "/open-apis/im/v1/messages/om_user/reply"
    )


async def test_rejected_card_falls_back_to_plain_text(harness: Any) -> None:
    await harness.start()
    harness.api.fail("send", (400, 230099))  # card content rejected

    await harness.channel.send(CHAT_ID, "内容")

    msg_types = [body["msg_type"] for body in harness.api.bodies("send")]
    assert msg_types == ["interactive", "text"]
    assert json.loads(harness.api.bodies("send")[-1]["content"]) == {"text": "内容"}


async def test_rate_limited_sends_are_retried(
    harness: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(feishu_api, "RETRY_BASE_DELAY_S", 0.0)
    await harness.start()
    harness.api.fail("send", (400, 230020), (429, 99991400))

    await harness.channel.send(CHAT_ID, "重要")

    assert [body["msg_type"] for body in harness.api.bodies("send")] == [
        "interactive",
        "interactive",
        "interactive",
    ]


async def test_failed_delivery_is_marked_and_raised(
    harness: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(feishu_api, "RETRY_BASE_DELAY_S", 0.0)
    await harness.start()
    harness.api.fail("send", *[(400, 230020)] * 4)

    with pytest.raises(feishu_api.FeishuApiError):
        await harness.channel._on_response(
            OutboundMessage(channel="feishu", chat_id=CHAT_ID, content="x")
        )

    assert harness.hub.deliveries == ["failed"]


async def test_images_and_files_are_uploaded_then_sent(
    harness: Any, tmp_path: Path
) -> None:
    await harness.start()
    image = tmp_path / "a.png"
    image.write_bytes(b"\x89PNG\r\n\x1a\n")
    document = tmp_path / "报告.txt"
    document.write_text("x", encoding="utf-8")

    await harness.channel.send_image(CHAT_ID, str(image))
    await harness.channel.send_file(CHAT_ID, str(document))

    assert harness.api.keys()[-4:] == ["upload_image", "send", "upload_file", "send"]
    image_body, file_body = harness.api.bodies("send")
    assert json.loads(image_body["content"]) == {"image_key": "img_1"}
    assert json.loads(file_body["content"]) == {"file_key": "file_1"}


def test_receive_ids_follow_the_id_prefix() -> None:
    assert resolve_receive_id("oc_1") == ("oc_1", "chat_id")
    assert resolve_receive_id("feishu:oc_1") == ("oc_1", "chat_id")
    assert resolve_receive_id("ou_1") == ("ou_1", "open_id")
    assert resolve_receive_id("on_1") == ("on_1", "union_id")


def test_configuration_key_covers_every_connection_setting() -> None:
    base = FeishuChannel("a", "s", "https://open.feishu.cn")

    assert (
        base.configuration_key
        == FeishuChannel("a", "s", "https://open.feishu.cn").configuration_key
    )
    for other in (
        FeishuChannel("b", "s", "https://open.feishu.cn"),
        FeishuChannel("a", "t", "https://open.feishu.cn"),
        FeishuChannel("a", "s", "https://open.larksuite.com"),
    ):
        assert other.configuration_key != base.configuration_key


def _reply_of(message_id: str, content: str) -> OutboundMessage:
    """A final reply of an inbound turn: it carries the inbound metadata."""
    return OutboundMessage(
        channel="feishu",
        chat_id=CHAT_ID,
        content=content,
        metadata={"message_id": message_id, "role_id": "mira"},
    )


async def test_final_reply_quotes_the_triggering_user_message(harness: Any) -> None:
    await harness.start()

    await harness.channel._on_response(_reply_of("om_user", "收到"))

    assert harness.api.keys() == ["reply"]
    [(_method, path, _body)] = [c for c in harness.api.calls if "/reply" in c[1]]
    assert path == "/open-apis/im/v1/messages/om_user/reply"


async def test_only_the_first_part_of_a_long_reply_quotes(harness: Any) -> None:
    await harness.start()
    text = "甲" * 3990 + "\n" + "乙" * 3990 + "\n" + "丙" * 10

    await harness.channel._on_response(_reply_of("om_user", text))

    assert harness.api.keys() == ["reply", "send", "send"]


async def test_proactive_messages_are_not_quoted(harness: Any) -> None:
    await harness.start()

    await harness.channel.send(CHAT_ID, "主动推送")
    await harness.channel._on_response(
        OutboundMessage(
            channel="feishu",
            chat_id=CHAT_ID,
            content="定时提醒",
            metadata={"role_id": "mira", "message_id": "not-a-feishu-id"},
        )
    )

    assert harness.api.keys() == ["send", "send"]


async def test_a_refused_quote_falls_back_to_a_plain_message(harness: Any) -> None:
    await harness.start()
    harness.api.fail("reply", (400, 230011))  # the quoted message was recalled

    await harness.channel._on_response(_reply_of("om_gone", "仍然送达"))

    assert harness.api.keys() == ["reply", "send"]
    assert harness.api.sent_texts()[-1] == "仍然送达"
    assert harness.hub.deliveries == ["sent"]


async def test_push_senders_return_the_first_platform_message_id(
    harness: Any, tmp_path: Path
) -> None:
    await harness.start()
    image = tmp_path / "a.png"
    image.write_bytes(b"\x89PNG\r\n\x1a\n")
    # The fake numbers every answered request, so ids follow request order.
    before = harness.api.counter

    first_id = await harness.channel.send(CHAT_ID, "\n".join(["段落" * 1000] * 3))
    cards = len(harness.api.bodies("send"))
    image_id = await harness.channel.send_image(CHAT_ID, str(image))

    # A multi-card text is identified by its first card, not its last.
    assert cards > 1
    assert first_id == f"om_{before + 1}"
    # After the text cards come the image upload and then the image message.
    assert image_id == f"om_{before + cards + 2}"
    assert await harness.channel.send(CHAT_ID, "  ") is None
