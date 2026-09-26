"""Outbound stream updates and safe fallback through a simulated QQ API."""

from __future__ import annotations

import asyncio
import json
from unittest.mock import Mock

import httpx
import pytest

from plugins.qqbot.backend.channel import QQBotChannel
from plugins.qqbot.backend.stream_delivery import _StreamState
from bus.events import OutboundMessage
from bus.errors import NonRetryableDeliveryError


@pytest.mark.parametrize("terminal", [False, True])
async def test_cancelled_delivery_retains_only_completed_receipt(terminal):
    entered = asyncio.Event()
    release = asyncio.Event()
    recalls = []

    async def handler(request):
        if request.url.path == "/app/getAppAccessToken":
            return httpx.Response(200, json={"access_token": "tok", "expires_in": 7200})
        if request.method == "DELETE":
            recalls.append(request.url.path)
            return httpx.Response(200, json={})
        assert request.url.path.endswith("/stream_messages")
        entered.set()
        await release.wait()
        return httpx.Response(200, json={"id": "outgoing-stream"})

    channel = QQBotChannel("app", "secret")
    await channel._client.aclose()
    channel._client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    channel._channel_hub = Mock()
    key = ("role:mira", "c2c:user", "incoming")
    if terminal:
        channel._live_states[key] = _StreamState(
            openid="user", msg_id="incoming", msg_seq=1
        )
    else:

        async def preview():
            await channel._send_live_stream(key, "c2c:user", "preview")

        channel._start_live_task(key, preview())
        await entered.wait()
    message = OutboundMessage(
        channel="qqbot",
        chat_id="c2c:user",
        content="final",
        metadata={
            "session_key_override": "role:mira",
            "external_message_id": "incoming",
        },
        committed_message_id="committed",
    )
    delivery = asyncio.create_task(channel._on_response(message))
    try:
        await asyncio.wait_for(entered.wait(), 1)
        await asyncio.sleep(0)
        delivery.cancel()
        await asyncio.sleep(0)
        assert not delivery.done()
        release.set()
        with pytest.raises(asyncio.CancelledError):
            await delivery
        channel._channel_hub.mark_delivery.assert_called_once_with(
            message,
            default_channel="qqbot",
            delivery_status="failed",
            external_message_id="outgoing-stream" if terminal else "",
        )
        assert recalls == (
            [] if terminal else ["/v2/users/user/messages/outgoing-stream"]
        )
        assert not channel._live_states
    finally:
        release.set()
        await channel._client.aclose()


@pytest.mark.parametrize(
    "mode", ["text", "images", "text_images", "stream", "fallback", "missing", "failed"]
)
async def test_reply_records_retained_receipt_instead_of_turn_id(mode):
    receipts = []

    def handler(request):
        if request.url.path == "/app/getAppAccessToken":
            return httpx.Response(200, json={"access_token": "tok", "expires_in": 7200})
        if request.method == "DELETE":
            return httpx.Response(200, json={})
        if request.url.path.endswith("/files"):
            return httpx.Response(200, json={"file_info": "file-1"})
        if mode == "failed" or (
            mode == "fallback" and request.url.path.endswith("/stream_messages")
        ):
            return httpx.Response(400)
        if mode == "missing":
            return httpx.Response(200, json={})
        message_id = (
            "stream-1"
            if request.url.path.endswith("/stream_messages")
            else f"sent-{len(receipts) + 1}"
        )
        receipts.append(message_id)
        return httpx.Response(200, json={"id": message_id})

    channel = QQBotChannel("app", "secret")
    await channel._client.aclose()
    channel._client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    hub = Mock()
    channel._channel_hub = hub
    if mode in {"stream", "fallback"}:
        channel._live_states[("role:mira", "c2c:user", "incoming")] = _StreamState(
            openid="user",
            msg_id="incoming",
            msg_seq=1,
            stream_msg_id="stream-1",
            index=1,
        )
    message = OutboundMessage(
        channel="qqbot",
        chat_id="c2c:user",
        content="" if mode == "images" else "reply",
        media=(
            ["https://example.test/one", "https://example.test/two"]
            if mode in {"images", "text_images"}
            else []
        ),
        metadata={
            "session_key_override": "role:mira",
            "external_message_id": "incoming",
        },
        committed_message_id="committed",
    )
    try:
        if mode == "failed":
            with pytest.raises(NonRetryableDeliveryError):
                await channel._on_response(message)
        else:
            await channel._on_response(message)
        hub.mark_delivery.assert_called_once_with(
            message,
            default_channel="qqbot",
            delivery_status="failed" if mode == "failed" else "sent",
            external_message_id=receipts[0] if receipts else "",
        )
        if mode == "fallback":
            assert receipts == ["sent-1"]
    finally:
        await channel._client.aclose()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("failure", "fail_at", "recall_fails", "should_raise"),
    [
        (None, 0, False, False),
        (400, 0, False, False),
        (400, 1, False, False),
        (400, 1, True, True),
        (408, 0, False, True),
        (500, 0, False, True),
        ("timeout", 0, False, True),
        ("timeout", 1, False, True),
        ("missing_id", 0, False, True),
    ],
)
async def test_send_stream_preserves_one_message_or_requires_confirmed_cleanup(
    failure: int | str | None, fail_at: int, recall_fails: bool, should_raise: bool
) -> None:
    calls: list[tuple[str, str, dict]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/app/getAppAccessToken":
            return httpx.Response(200, json={"access_token": "tok", "expires_in": 7200})
        body = json.loads(request.content) if request.content else {}
        calls.append((request.method, request.url.path, body))
        if request.url.path.endswith("/stream_messages"):
            if body["index"] >= fail_at and failure is not None:
                if failure == "timeout":
                    raise httpx.ReadTimeout("response lost", request=request)
                if failure == "missing_id":
                    return httpx.Response(200, json={})
                assert isinstance(failure, int)
                return httpx.Response(failure)
            return httpx.Response(200, json={"id": "stream-1"})
        if request.method == "DELETE" and recall_fails:
            return httpx.Response(500)
        return httpx.Response(200, json={"id": "normal-1"})

    channel = QQBotChannel("app", "secret")
    await channel._client.aclose()
    channel._client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    channel._last_c2c_msg_id["user-1"] = "inbound-1"
    message = "分段内容" * 90
    try:
        if should_raise:
            with pytest.raises((httpx.HTTPError, RuntimeError)):
                await channel.send_stream("c2c:user-1", message)
        else:
            await channel.send_stream("c2c:user-1", message)
        ordinary = [body for method, path, body in calls if path.endswith("/messages")]
        if should_raise or failure is None:
            assert ordinary == []
        else:
            assert [body["markdown"]["content"] for body in ordinary] == [message]
            if fail_at:
                assert calls[-2][:2] == ("DELETE", "/v2/users/user-1/messages/stream-1")
        streams = [body for _, path, body in calls if path.endswith("/stream_messages")]
        if failure is None:
            assert [body.get("stream_msg_id") for body in streams] == [
                None,
                "stream-1",
                "stream-1",
            ]
            assert [body["index"] for body in streams] == [0, 1, 2]
            assert streams[-1]["input_state"] == 10
            assert streams[-1]["content_raw"] == message
    finally:
        await channel._client.aclose()


@pytest.mark.asyncio
async def test_push_recovers_rejected_continuation_in_place() -> None:
    bodies: list[dict] = []

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/app/getAppAccessToken":
            return httpx.Response(200, json={"access_token": "tok", "expires_in": 7200})
        assert request.url.path.endswith("/stream_messages")
        body = json.loads(request.content)
        bodies.append(body)
        if len(bodies) == 2:
            return httpx.Response(429)
        return httpx.Response(200, json={"id": "stream-1"})

    channel = QQBotChannel("app", "secret")
    await channel._client.aclose()
    channel._client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    channel._last_c2c_msg_id["user-1"] = "inbound-1"
    message = "分段内容" * 90
    try:
        await channel.send_stream("c2c:user-1", message)
        assert [(b["index"], b["input_state"]) for b in bodies] == [
            (0, 1),
            (1, 1),
            (1, 10),
        ]
        assert bodies[-1]["stream_msg_id"] == "stream-1"
        assert bodies[-1]["content_raw"] == message
    finally:
        await channel._client.aclose()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("cancel_index", "recall_fails"), [(0, False), (1, False), (2, False), (1, True)]
)
async def test_cancelled_push_recalls_only_acknowledged_incomplete_stream(
    cancel_index: int, recall_fails: bool, caplog: pytest.LogCaptureFixture
) -> None:
    entered = asyncio.Event()
    release = asyncio.Event()
    calls: list[tuple[str, str, dict]] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/app/getAppAccessToken":
            return httpx.Response(200, json={"access_token": "tok", "expires_in": 7200})
        body = json.loads(request.content) if request.content else {}
        calls.append((request.method, request.url.path, body))
        if request.url.path.endswith("/stream_messages"):
            if body["index"] == cancel_index:
                entered.set()
                await release.wait()
            return httpx.Response(200, json={"id": "stream-1"})
        assert request.method == "DELETE"
        return httpx.Response(500 if recall_fails else 200)

    channel = QQBotChannel("app", "secret")
    await channel._client.aclose()
    channel._client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    channel._last_c2c_msg_id["user-1"] = "inbound-1"
    push = asyncio.create_task(channel.send_stream("c2c:user-1", "分段内容" * 90))
    try:
        await asyncio.wait_for(entered.wait(), 1)
        push.cancel()
        release.set()
        with pytest.raises(asyncio.CancelledError):
            await asyncio.wait_for(push, 1)
        streams = [body for _, path, body in calls if path.endswith("/stream_messages")]
        assert [body["index"] for body in streams] == list(range(cancel_index + 1))
        deletes = [(method, path) for method, path, _ in calls if method == "DELETE"]
        assert deletes == (
            [("DELETE", "/v2/users/user-1/messages/stream-1")]
            if cancel_index < 2
            else []
        )
        assert not any(path.endswith("/messages") for _, path, _ in calls)
        if recall_fails:
            assert "取消投递后撤回流式预览失败" in caplog.text
    finally:
        release.set()
        await channel._client.aclose()
