"""QQBot live delivery policy using public SDK events and fake external HTTP."""

from __future__ import annotations

import asyncio
import json
from datetime import datetime
from pathlib import Path

import httpx
import pytest

from shiori_sdk.testing.channel_context import fake_channel_context
from shiori_sdk.testing.channel_hub import FakeChannelHub
from shiori_sdk.testing.channel_services import FakeMessageBus
from shiori_sdk.testing.events import FakeEvents
from shiori_sdk.messages import InboundMessage, OutboundMessage
from shiori_sdk.channel_events import StreamDeltaReady, TurnCancelled, TurnStarted
from shiori_sdk.channels.errors import NonRetryableDeliveryError
import plugins.qqbot.backend.streaming as qqbot_streaming
from plugins.qqbot.backend.channel import QQBotChannel

SESSION_KEY = "role:mira"
CHAT_ID = "c2c:app:user-1"

STREAM_PATH = "/v2/users/user-1/stream_messages"
MESSAGE_PATH = "/v2/users/user-1/messages"


class QQBotHttp:
    """Answers the official QQBot HTTP API offline and models stream expiry."""

    def __init__(self) -> None:
        self.calls: list[tuple[str, str, dict[str, object]]] = []
        self.fail_stream_from: int | None = None

    def handler(self, request: httpx.Request) -> httpx.Response:
        """Answer authentication, discovery and message requests without network IO."""
        if request.url.path == "/app/getAppAccessToken":
            return httpx.Response(200, json={"access_token": "tok", "expires_in": 7200})
        if request.url.path == "/gateway":
            return httpx.Response(200, json={"url": "wss://gateway.invalid"})
        body = json.loads(request.content) if request.content else {}
        assert isinstance(body, dict)
        self.calls.append((request.method, request.url.path, body))
        if request.url.path == STREAM_PATH:
            if (
                self.fail_stream_from is not None
                and len(self.stream_bodies()) > self.fail_stream_from
            ):
                return httpx.Response(400, json={"message": "stream expired"})
            return httpx.Response(200, json={"id": "stream-1"})
        return httpx.Response(200, json={})

    def stream_bodies(self) -> list[dict[str, object]]:
        """Return stream payloads in their request order, including rejected calls."""
        return [body for _method, path, body in self.calls if path == STREAM_PATH]

    def markdown_messages(self) -> list[str]:
        """Return final Markdown content sent through the ordinary message API."""
        messages: list[str] = []
        for method, path, body in self.calls:
            if method == "POST" and path == MESSAGE_PATH and "markdown" in body:
                markdown = body["markdown"]
                assert isinstance(markdown, dict)
                content = markdown["content"]
                assert isinstance(content, str)
                messages.append(content)
        return messages


async def _started_channel(
    api: QQBotHttp, tmp_path: Path, bus: FakeMessageBus | None = None
) -> tuple[QQBotChannel, FakeEvents, FakeChannelHub, InboundMessage]:
    channel = QQBotChannel("app", "secret")
    channel._client = httpx.AsyncClient(transport=httpx.MockTransport(api.handler))

    async def _no_gateway() -> None:
        return None

    channel._gateway_loop = _no_gateway
    event_bus = FakeEvents()
    # Routes like the real hub: the reply runs on the bound role's session.
    hub = FakeChannelHub(session_key=SESSION_KEY)
    bus = bus if bus is not None else FakeMessageBus()
    await channel.start(
        fake_channel_context(tmp_path, bus=bus, event_bus=event_bus, channel_hub=hub)
    )
    await channel._handle_c2c(
        {"id": "msg-1", "author": {"user_openid": "user-1"}, "content": "天气如何"}
    )
    await channel._intake.drain()
    [inbound] = bus.inbound[-1:]
    await event_bus.emit(
        TurnStarted(
            session_key=SESSION_KEY,
            channel="qqbot",
            chat_id=CHAT_ID,
            content=inbound.content,
            timestamp=datetime.now(),
            external_message_id="msg-1",
        )
    )
    return channel, event_bus, hub, inbound


def _stream_sink(channel: QQBotChannel, event_bus: FakeEvents, inbound: InboundMessage):
    """Emit the public stream contract; real AgentLoop wiring is covered by host tests."""
    if not channel.supports_stream_events(inbound.chat_id):
        return None

    async def emit(content: str) -> None:
        await event_bus.emit(
            StreamDeltaReady(
                session_key=inbound.session_key,
                channel=inbound.channel,
                chat_id=inbound.chat_id,
                content_delta=content,
                external_message_id=str(
                    inbound.metadata.get("external_message_id", "")
                ),
            )
        )

    return emit


def _assert_no_turn_state(channel: QQBotChannel) -> None:
    """A finished or abandoned turn leaves no preview state behind."""
    assert channel._live_states == {}
    assert channel._reply_buffers == {}
    assert channel._live_stop_events == {}
    assert channel._live_tasks == set()


async def _stop_without_further_requests(channel: QQBotChannel, api: QQBotHttp) -> None:
    """Stopping after the turn ended must not issue late preview writes or recalls."""
    calls = len(api.calls)
    await channel.stop()
    assert api.calls[calls:] == []


def _final_reply(content: str) -> OutboundMessage:
    return OutboundMessage(
        channel="qqbot",
        chat_id=CHAT_ID,
        content=content,
        metadata={
            "role_id": "mira",
            "session_key_override": SESSION_KEY,
            "external_message_id": "msg-1",
        },
    )


def test_qqbot_opts_c2c_chats_into_stream_events_and_prompt_rules() -> None:
    channel = QQBotChannel("app", "secret")

    assert channel.supports_stream_events("c2c:app:user-1")
    assert not channel.supports_stream_events("c2c:other-app:user-1")
    assert not channel.supports_stream_events("group:group-1")
    assert not channel.supports_stream_events("bogus:x")
    hint = channel.system_prompt_hint("c2c:app:user-1")
    assert hint.startswith("## 官方 QQBot 渠道规则（硬性）")
    assert "`channel=qqbot`" in hint
    assert "c2c:<app_id>:<user_openid>" in hint


@pytest.mark.asyncio
async def test_qqbot_turn_streams_a_live_preview_then_finishes_it_in_place(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setattr(qqbot_streaming, "LIVE_STREAM_MIN_INTERVAL_S", 0.01)
    api = QQBotHttp()
    channel, event_bus, hub, inbound = await _started_channel(api, tmp_path)
    sink = _stream_sink(channel, event_bus, inbound)
    assert sink is not None

    # Deltas arriving while a refresh is pending coalesce into one request.
    await sink("今天")
    await sink("晴，")
    await channel._drain_live_tasks()
    await sink("最高 25 度")
    await channel._drain_live_tasks()
    await channel._on_response(_final_reply("今天晴，最高 25 度。"))

    bodies = api.stream_bodies()
    assert [
        (b["index"], b["input_state"], b["content_raw"], b.get("stream_msg_id"))
        for b in bodies
    ] == [
        (0, 1, "今天晴，", None),
        (1, 1, "今天晴，最高 25 度", "stream-1"),
        (2, 10, "今天晴，最高 25 度。", "stream-1"),
    ]
    assert {(b["msg_id"], b["event_id"], b["msg_seq"]) for b in bodies} == {
        ("msg-1", "msg-1", bodies[0]["msg_seq"])
    }
    assert api.markdown_messages() == []
    assert hub.delivery_statuses() == ["sent"]
    _assert_no_turn_state(channel)
    await channel.stop()


@pytest.mark.asyncio
@pytest.mark.parametrize("final_queued", [False, True])
async def test_cancelled_turn_keeps_its_preview_only_for_a_queued_final(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, final_queued: bool
) -> None:
    monkeypatch.setattr(qqbot_streaming, "LIVE_STREAM_MIN_INTERVAL_S", 0)
    api = QQBotHttp()
    bus = FakeMessageBus()
    channel, event_bus, hub, inbound = await _started_channel(api, tmp_path, bus)
    sink = _stream_sink(channel, event_bus, inbound)
    assert sink is not None
    await sink("取消前的预览")
    await channel._drain_live_tasks()
    if final_queued:
        bus.pending_outbound.add(("qqbot", CHAT_ID, "msg-1"))

    await event_bus.emit(TurnCancelled(SESSION_KEY, "qqbot", CHAT_ID, "msg-1"))

    recalls = [path for method, path, _body in api.calls if method == "DELETE"]
    if final_queued:
        # The committed reply still owns the preview and finishes it in place.
        assert recalls == []
        assert set(channel._live_states) == {(SESSION_KEY, CHAT_ID, "msg-1")}
        bus.pending_outbound.clear()
        await channel._on_response(_final_reply("已经提交的完整回复"))
        assert hub.delivery_statuses() == ["sent"]
        assert api.stream_bodies()[-1]["input_state"] == 10
    else:
        assert recalls == ["/v2/users/user-1/messages/stream-1"]
    _assert_no_turn_state(channel)
    await channel.stop()


@pytest.mark.asyncio
async def test_old_final_after_a_newer_turn_clears_only_its_own_turn(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(qqbot_streaming, "LIVE_STREAM_MIN_INTERVAL_S", 0)
    api = QQBotHttp()
    bus = FakeMessageBus()
    channel, event_bus, hub, first = await _started_channel(api, tmp_path, bus)
    first_sink = _stream_sink(channel, event_bus, first)
    assert first_sink is not None
    await first_sink("第一轮预览")
    await channel._drain_live_tasks()

    await channel._handle_c2c(
        {"id": "msg-2", "author": {"user_openid": "user-1"}, "content": "第二问"}
    )
    await channel._intake.drain()
    second = bus.inbound[-1]
    await event_bus.emit(
        TurnStarted(
            session_key=SESSION_KEY,
            channel="qqbot",
            chat_id=CHAT_ID,
            content=second.content,
            timestamp=datetime.now(),
            external_message_id="msg-2",
        )
    )
    second_sink = _stream_sink(channel, event_bus, second)
    assert second_sink is not None
    await second_sink("第二轮预览")
    await channel._drain_live_tasks()

    await channel._on_response(_final_reply("第一轮完整回复"))
    assert set(channel._live_states) == {(SESSION_KEY, CHAT_ID, "msg-2")}
    second_reply = _final_reply("第二轮完整回复")
    second_reply.metadata["external_message_id"] = "msg-2"
    await channel._on_response(second_reply)

    assert hub.delivery_statuses() == ["sent", "sent"]
    _assert_no_turn_state(channel)
    await channel.stop()


@pytest.mark.asyncio
async def test_newer_inbound_before_the_first_delta_keeps_each_turns_stream(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(qqbot_streaming, "LIVE_STREAM_MIN_INTERVAL_S", 0)
    api = QQBotHttp()
    bus = FakeMessageBus()
    channel, event_bus, hub, first = await _started_channel(api, tmp_path, bus)

    def handler(request: httpx.Request) -> httpx.Response:
        result = api.handler(request)
        if request.url.path == STREAM_PATH:
            body = json.loads(request.content)
            return httpx.Response(200, json={"id": f"stream-{body['msg_id']}"})
        return result

    channel._client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    # The newer message changes the chat's latest anchor before the old turn
    # emits anything; the old turn's events still own msg-1.
    await channel._handle_c2c(
        {"id": "msg-2", "author": {"user_openid": "user-1"}, "content": "第二问"}
    )
    await channel._intake.drain()
    second = bus.inbound[-1]
    first_sink = _stream_sink(channel, event_bus, first)
    second_sink = _stream_sink(channel, event_bus, second)
    assert first_sink is not None and second_sink is not None
    await first_sink("第一轮预览")
    await channel._drain_live_tasks()
    # The old final is still queued when the next turn starts.
    bus.pending_outbound.add(("qqbot", CHAT_ID, "msg-1"))
    await event_bus.emit(
        TurnStarted(
            session_key=SESSION_KEY,
            channel="qqbot",
            chat_id=CHAT_ID,
            content=second.content,
            timestamp=datetime.now(),
            external_message_id="msg-2",
        )
    )
    await second_sink("第二轮预览")
    await channel._drain_live_tasks()
    bus.pending_outbound.clear()

    await channel._on_response(_final_reply("第一轮完整回复"))
    second_reply = _final_reply("第二轮完整回复")
    second_reply.metadata["external_message_id"] = "msg-2"
    await channel._on_response(second_reply)

    assert [
        (body["msg_id"], body["index"], body["input_state"], body.get("stream_msg_id"))
        for body in api.stream_bodies()
    ] == [
        ("msg-1", 0, 1, None),
        ("msg-2", 0, 1, None),
        ("msg-1", 1, 10, "stream-msg-1"),
        ("msg-2", 1, 10, "stream-msg-2"),
    ]
    assert api.markdown_messages() == []
    assert hub.delivery_statuses() == ["sent", "sent"]
    _assert_no_turn_state(channel)
    await _stop_without_further_requests(channel, api)


@pytest.mark.asyncio
async def test_qqbot_final_reply_cancels_a_throttled_refresh(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setattr(qqbot_streaming, "LIVE_STREAM_MIN_INTERVAL_S", 60.0)
    api = QQBotHttp()
    channel, event_bus, _hub, inbound = await _started_channel(api, tmp_path)
    sink = _stream_sink(channel, event_bus, inbound)
    assert sink is not None

    await sink("第一段")
    await channel._drain_live_tasks()
    await sink("第二段")  # waits for the 60 s interval
    await asyncio.sleep(0)  # let the refresh enter its throttled wait
    await asyncio.wait_for(channel._on_response(_final_reply("第一段第二段")), 1)
    await channel._drain_live_tasks()

    assert [(b["index"], b["input_state"]) for b in api.stream_bodies()] == [
        (0, 1),
        (1, 10),
    ]
    assert channel._live_tasks == set()
    await channel.stop()


@pytest.mark.asyncio
@pytest.mark.parametrize("blocked_index", [0, 1])
async def test_final_reply_waits_for_inflight_stream_id_and_index(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, blocked_index: int
) -> None:
    monkeypatch.setattr(qqbot_streaming, "LIVE_STREAM_MIN_INTERVAL_S", 0)
    api = QQBotHttp()
    channel, event_bus, hub, inbound = await _started_channel(api, tmp_path)
    entered = asyncio.Event()
    release = asyncio.Event()

    async def handler(request: httpx.Request) -> httpx.Response:
        result = api.handler(request)
        if request.url.path == STREAM_PATH:
            body = json.loads(request.content)
            if body["index"] == blocked_index and body["input_state"] == 1:
                entered.set()
                await release.wait()
        return result

    channel._client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    sink = _stream_sink(channel, event_bus, inbound)
    assert sink is not None
    if blocked_index:
        await sink("第一段")
        await channel._drain_live_tasks()
    await sink("第二段")
    await asyncio.wait_for(entered.wait(), 1)
    final = asyncio.create_task(channel._on_response(_final_reply("完整回复")))
    try:
        await asyncio.sleep(0)
        assert not final.done()
        release.set()
        await asyncio.wait_for(final, 1)
        bodies = api.stream_bodies()
        assert [body["index"] for body in bodies] == list(range(blocked_index + 2))
        assert [body.get("stream_msg_id") for body in bodies] == [None] + [
            "stream-1"
        ] * (blocked_index + 1)
        assert bodies[-1]["input_state"] == 10
        assert bodies[-1]["content_raw"] == "完整回复"
        assert api.markdown_messages() == []
        assert hub.delivery_statuses() == ["sent"]
    finally:
        release.set()
        await final
        await channel.stop()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "failure",
    ["timeout", "server", "missing_id", "recall", "fallback_timeout", "image"],
)
async def test_uncertain_stream_or_failed_recall_never_resends_or_marks_sent(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, failure: str
) -> None:
    monkeypatch.setattr(qqbot_streaming, "LIVE_STREAM_MIN_INTERVAL_S", 0)
    api = QQBotHttp()
    channel, event_bus, hub, inbound = await _started_channel(api, tmp_path)

    def handler(request: httpx.Request) -> httpx.Response:
        result = api.handler(request)
        if request.url.path == STREAM_PATH:
            if failure == "timeout":
                raise httpx.ReadTimeout("response lost", request=request)
            if failure == "server":
                return httpx.Response(500)
            if failure == "missing_id":
                return httpx.Response(200, json={})
            if failure == "fallback_timeout":
                return httpx.Response(400)
            if failure == "recall" and json.loads(request.content)["input_state"] == 10:
                return httpx.Response(400)
        if request.method == "DELETE":
            return httpx.Response(500)
        if failure == "fallback_timeout" and request.url.path == MESSAGE_PATH:
            raise httpx.ReadTimeout("plain receipt lost", request=request)
        if request.url.path.endswith("/files"):
            return httpx.Response(500)
        return result

    channel._client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    sink = _stream_sink(channel, event_bus, inbound)
    assert sink is not None
    reply = _final_reply("半句话。")
    if failure == "image":
        # The text already streamed; only the following image upload fails.
        reply.media = ["https://example.invalid/image.png"]
    try:
        await sink("半句")
        await channel._drain_live_tasks()
        # A replay could duplicate the preview, the fallback or an earlier part.
        with pytest.raises(NonRetryableDeliveryError):
            await channel._on_response(reply)
        assert api.markdown_messages() == (
            ["半句话。"] if failure == "fallback_timeout" else []
        )
        assert hub.delivery_statuses() == ["failed"]
        assert channel._live_states == {}
        assert channel._live_tasks == set()
        await _stop_without_further_requests(channel, api)
    finally:
        await channel.stop()


@pytest.mark.asyncio
@pytest.mark.parametrize("cancel_terminal", [False, True])
@pytest.mark.parametrize("request_fails", [False, True])
async def test_cancelled_final_delivery_waits_for_receipt_and_never_marks_sent(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    caplog: pytest.LogCaptureFixture,
    cancel_terminal: bool,
    request_fails: bool,
) -> None:
    monkeypatch.setattr(qqbot_streaming, "LIVE_STREAM_MIN_INTERVAL_S", 0)
    api = QQBotHttp()
    channel, event_bus, hub, inbound = await _started_channel(api, tmp_path)
    entered = asyncio.Event()
    release = asyncio.Event()

    async def handler(request: httpx.Request) -> httpx.Response:
        result = api.handler(request)
        if request.url.path == STREAM_PATH:
            terminal = json.loads(request.content)["input_state"] == 10
            if terminal == cancel_terminal:
                entered.set()
                await release.wait()
                if request_fails:
                    return httpx.Response(500)
        if request.method == "DELETE":
            # The recall itself fails: nothing may be replayed after it.
            return httpx.Response(500)
        return result

    channel._client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    sink = _stream_sink(channel, event_bus, inbound)
    assert sink is not None
    await sink("半句")
    if cancel_terminal:
        await channel._drain_live_tasks()
    final = asyncio.create_task(channel._on_response(_final_reply("半句话。")))
    try:
        await asyncio.wait_for(entered.wait(), 1)
        await asyncio.sleep(0)
        final.cancel()
        await asyncio.sleep(0)
        assert not final.done()
        release.set()
        with pytest.raises(asyncio.CancelledError):
            await asyncio.wait_for(final, 3)
        assert hub.delivery_statuses() == ["failed"]
        assert api.markdown_messages() == []
        assert channel._live_tasks == set()
        assert channel._live_states == {}
        # Only an acknowledged, unfinished preview is recalled.
        recall_attempted = cancel_terminal == request_fails
        recalls = [call[:2] for call in api.calls if call[0] == "DELETE"]
        assert recalls == (
            [("DELETE", "/v2/users/user-1/messages/stream-1")]
            if recall_attempted
            else []
        )
        if recall_attempted:
            assert "取消投递后撤回流式预览失败" in caplog.text
        if cancel_terminal and request_fails:
            assert "取消流式投递后等待发送回执失败" in caplog.text
        await _stop_without_further_requests(channel, api)
    finally:
        release.set()
        await channel.stop()


@pytest.mark.asyncio
async def test_qqbot_withdraws_a_broken_preview_before_the_fallback_message(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setattr(qqbot_streaming, "LIVE_STREAM_MIN_INTERVAL_S", 0.01)
    api = QQBotHttp()
    api.fail_stream_from = 1
    channel, event_bus, hub, inbound = await _started_channel(api, tmp_path)
    sink = _stream_sink(channel, event_bus, inbound)
    assert sink is not None

    await sink("半句")
    await channel._drain_live_tasks()
    await sink("话")  # rejected: the preview is disabled for this turn
    await channel._drain_live_tasks()
    await channel._on_response(_final_reply("半句话。"))

    assert [(method, path) for method, path, _body in api.calls][-2:] == [
        ("DELETE", "/v2/users/user-1/messages/stream-1"),
        ("POST", MESSAGE_PATH),
    ]
    assert len(api.stream_bodies()) == 3
    assert api.markdown_messages() == ["半句话。"]
    assert hub.delivery_statuses() == ["sent"]
    await channel.stop()


@pytest.mark.asyncio
async def test_qqbot_group_chats_do_not_get_stream_events() -> None:
    channel = QQBotChannel("app", "secret")
    group = InboundMessage(
        channel="qqbot", sender="u", chat_id="group:g1", content="hi"
    )

    assert _stream_sink(channel, FakeEvents(), group) is None


@pytest.mark.asyncio
async def test_rejected_first_preview_safely_falls_back_once(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setattr(qqbot_streaming, "LIVE_STREAM_MIN_INTERVAL_S", 0)
    api = QQBotHttp()
    api.fail_stream_from = 0
    channel, event_bus, hub, inbound = await _started_channel(api, tmp_path)
    sink = _stream_sink(channel, event_bus, inbound)
    assert sink is not None
    try:
        await sink("半句")
        await channel._drain_live_tasks()
        await channel._on_response(_final_reply("半句话。"))
        assert len(api.stream_bodies()) == 1
        assert api.markdown_messages() == ["半句话。"]
        assert not any(method == "DELETE" for method, _, _ in api.calls)
        assert hub.delivery_statuses() == ["sent"]
    finally:
        await channel.stop()
