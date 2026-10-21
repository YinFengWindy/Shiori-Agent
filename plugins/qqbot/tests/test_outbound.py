"""Outbound reply delivery and receipts through a simulated QQ API."""

from __future__ import annotations

import asyncio
import httpx
import pytest

from plugins.qqbot.backend.channel import QQBotChannel
from plugins.qqbot.backend.stream_delivery import _StreamState
from shiori_sdk.messages import DeliveryOutcome, OutboundMessage
from shiori_sdk.channels.errors import NonRetryableDeliveryError
from shiori_sdk.testing.channel_hub import FakeChannelHub


def _receipts(hub: FakeChannelHub) -> list[tuple[object, object, object]]:
    return [
        (item["delivery_status"], item["external_message_id"], item["via_account"])
        for item in hub.deliveries
    ]


async def test_natural_messages_send_separately_without_stream_requests():
    paths = []

    def handler(request):
        if request.url.path == "/app/getAppAccessToken":
            return httpx.Response(200, json={"access_token": "tok", "expires_in": 7200})
        paths.append(request.url.path)
        return httpx.Response(200, json={"id": f"reply-{len(paths)}"})

    channel = QQBotChannel("app", "secret")
    channel._client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    channel._channel_hub = FakeChannelHub()
    messages = [
        OutboundMessage(
            "qqbot",
            "c2c:app:user",
            content,
            metadata={"reply_sequence_id": "turn", "reply_sequence_index": index},
            committed_message_id=f"row-{index}",
        )
        for index, content in enumerate(("one", "two"))
    ]
    try:
        for message in messages:
            await channel._on_response(message)
    finally:
        await channel._client.aclose()
    assert paths == ["/v2/users/user/messages"] * 2
    assert [message.delivery_outcome for message in messages] == [
        DeliveryOutcome("sent", "reply-1"),
        DeliveryOutcome("sent", "reply-2"),
    ]


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
    channel._client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    hub = FakeChannelHub()
    channel._channel_hub = hub
    key = ("role:mira", "c2c:app:user", "incoming")
    if terminal:
        channel._live_states[key] = _StreamState(
            openid="user", msg_id="incoming", msg_seq=1
        )
    else:

        async def preview():
            await channel._send_live_stream(key, "c2c:app:user", "preview")

        channel._start_live_task(key, preview())
        await entered.wait()
    message = OutboundMessage(
        channel="qqbot",
        chat_id="c2c:app:user",
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
        assert _receipts(hub) == [
            ("failed", "outgoing-stream" if terminal else "", None)
        ]
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

    via = {
        "platform": "qqbot",
        "platform_account_id": "app",
        "display_name": "Bot",
        "prefix": "QQ 机器人「Bot」（AppID app）",
    }
    channel = QQBotChannel("app", "secret", via_account=lambda: via)
    channel._client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    hub = FakeChannelHub()
    channel._channel_hub = hub
    if mode in {"stream", "fallback"}:
        channel._live_states[("role:mira", "c2c:app:user", "incoming")] = _StreamState(
            openid="user",
            msg_id="incoming",
            msg_seq=1,
            stream_msg_id="stream-1",
            index=1,
        )
    message = OutboundMessage(
        channel="qqbot",
        chat_id="c2c:app:user",
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
        # Only a sent reply records the account it went out through.
        assert _receipts(hub) == [
            (
                "failed" if mode == "failed" else "sent",
                receipts[0] if receipts else "",
                None if mode == "failed" else via,
            )
        ]
        if mode == "fallback":
            assert receipts == ["sent-1"]
    finally:
        await channel._client.aclose()
