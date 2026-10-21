"""Actual QQBot HTTP, bus lanes and SQLite agree on each visible reply segment."""

import asyncio
import json
from contextlib import asynccontextmanager

import httpx
import pytest

from agent.turns.channel_sequence import ChannelSequenceOwner
from agent.turns.channel_sequence_commit import (
    ChannelSequenceDeliveryError,
    commit_channel_reply_sequence,
)
from agent.turns.reply_sequence import ReplySequence
from bus.queue import MessageBus
from conversation.context_scope import ContextView, UserContextThreads
from core.roles.role_runtime import RoleExecutionContext, RoleRuntime
from core.roles.store import RoleStore
from plugins.qqbot.backend.channel import QQBotChannel
from session.manager import SessionManager
from session.manager.models import build_session_message, whole_session
from shiori_sdk.channels.threads import network_thread_id


@asynccontextmanager
async def transport(handler):
    bus = MessageBus(outbound_retry_delay_s=0)
    channel = QQBotChannel("app", "secret")

    async def request(req):
        if req.url.path == "/app/getAppAccessToken":
            return httpx.Response(
                200, json={"access_token": "token", "expires_in": 7200}
            )
        return await handler(req)

    channel._client = httpx.AsyncClient(transport=httpx.MockTransport(request))
    bus.subscribe_outbound("qqbot", channel._on_response, supports_reply_sequence=True)
    dispatch = asyncio.create_task(bus.dispatch_outbound())
    try:
        yield bus
    finally:
        dispatch.cancel()
        await asyncio.gather(dispatch, return_exceptions=True)
        await channel._client.aclose()


async def batch(
    manager,
    bus,
    owner,
    *,
    chat="a",
    texts=("one", "two", "three"),
    state=None,
    tool_chain=None,
):
    session = manager.get_or_create("role:mira")
    thread = network_thread_id("mira", "qqbot", f"c2c:app:{chat}")
    metadata = {
        "role_id": "mira",
        "thread_id": thread,
        "transport_channel": "qqbot",
        "transport_chat_id": f"c2c:app:{chat}",
        "session_key_override": session.key,
        "external_message_id": f"incoming-{chat}",
        "request_id": f"turn-{chat}",
    }
    messages = [
        build_session_message("user", "hi", metadata=metadata, thread_id=thread)
    ]
    messages.extend(
        build_session_message(
            "assistant",
            text,
            thread_id=thread,
            metadata={
                **metadata,
                "reply_sequence_id": f"turn-{chat}",
                "reply_sequence_index": index,
            },
        )
        for index, text in enumerate(texts)
    )
    if tool_chain:
        messages[1]["tool_chain"] = tool_chain
    with owner.bind(bus):
        await commit_channel_reply_sequence(
            manager=manager,
            session=session,
            messages=messages,
            sequence=ReplySequence(texts),
            state_kwargs=state or {"pending_messages": True},
            metadata=metadata,
            channel="qqbot",
            chat_id=f"c2c:app:{chat}",
            extra_media=[],
        )


async def test_order_and_per_segment_receipts_survive_reload(tmp_path, monkeypatch):
    sent = []
    manager = SessionManager(tmp_path)

    async def request(req):
        sent.append(json.loads(req.content)["markdown"]["content"])
        # The current pending message is private to delivery, not model history.
        visible = manager.get_or_create("role:mira").get_history(include=whole_session)
        assert [m["content"] for m in visible if m["role"] == "assistant"] == sent[:-1]
        return httpx.Response(200, json={"id": f"out-{len(sent)}"})

    async def pause(_):
        assert sent

    monkeypatch.setattr("agent.turns.reply_sequence.wait_between_messages", pause)
    async with transport(request) as bus:
        await batch(manager, bus, ChannelSequenceOwner())
    rows = SessionManager(tmp_path).get_or_create("role:mira").messages
    replies = [m for m in rows if m["role"] == "assistant"]
    assert sent == ["one", "two", "three"]
    assert [r["external_message_id"] for r in replies] == ["out-1", "out-2", "out-3"]
    assert [r["delivery_status"] for r in replies] == ["sent"] * 3
    assert len({r["id"] for r in replies}) == 3
    assert {r["metadata"]["trigger_user_message_id"] for r in replies} == {
        rows[0]["id"]
    }


async def test_unknown_second_send_keeps_prefix_and_never_replays(
    tmp_path, monkeypatch
):
    sent = []

    async def request(req):
        sent.append(json.loads(req.content)["markdown"]["content"])
        if len(sent) == 2:
            raise httpx.ReadTimeout("platform outcome unknown")
        return httpx.Response(200, json={"id": "first"})

    async def pause(_):
        pass

    monkeypatch.setattr("agent.turns.reply_sequence.wait_between_messages", pause)
    async with transport(request) as bus:
        with pytest.raises(ChannelSequenceDeliveryError, match="uncertain"):
            await batch(SessionManager(tmp_path), bus, ChannelSequenceOwner())
    session = SessionManager(tmp_path).get_or_create("role:mira")
    replies = [m for m in session.messages if m["role"] == "assistant"]
    assert sent == ["one", "two"]
    assert [r["delivery_status"] for r in replies] == ["sent", "uncertain"]
    assert [
        m["content"]
        for m in session.get_history(include=whole_session)
        if m["role"] == "assistant"
    ] == ["one"]
    view = ContextView("external", UserContextThreads("mira", frozenset()))
    assert view.includes(replies[0])
    assert not view.includes(replies[1])


async def test_unknown_first_send_preserves_executed_tool_facts(tmp_path):
    async def request(_):
        raise httpx.ReadTimeout("unknown")

    chain = [
        {
            "text": "",
            "calls": [
                {
                    "call_id": "call",
                    "name": "lookup",
                    "arguments": {},
                    "result": "already executed",
                }
            ],
        }
    ]
    async with transport(request) as bus:
        with pytest.raises(ChannelSequenceDeliveryError):
            await batch(
                SessionManager(tmp_path), bus, ChannelSequenceOwner(), tool_chain=chain
            )
    history = (
        SessionManager(tmp_path)
        .get_or_create("role:mira")
        .get_history(include=whole_session)
    )
    assert any(message.get("tool_calls") for message in history)
    assert any(message.get("content") == "already executed" for message in history)
    assert not any(
        message.get("content") in {"one", "two", "three"} for message in history
    )


async def test_cancellation_finishes_started_send_and_late_receipt_only(tmp_path):
    entered, release = asyncio.Event(), asyncio.Event()
    sent = []
    owner = ChannelSequenceOwner()

    async def request(req):
        sent.append(json.loads(req.content)["markdown"]["content"])
        entered.set()
        await release.wait()
        return httpx.Response(200, json={"id": "late-receipt"})

    async with transport(request) as bus:
        task = asyncio.create_task(batch(SessionManager(tmp_path), bus, owner))
        await asyncio.wait_for(entered.wait(), 1)
        owner.stop()
        await asyncio.sleep(0)
        assert not task.done()
        release.set()
        with pytest.raises(asyncio.CancelledError):
            await task
    rows = SessionManager(tmp_path).get_or_create("role:mira").messages
    assert sent == ["one"]
    assert len(rows) == 2
    assert rows[-1]["delivery_status"] == "sent"
    assert rows[-1]["external_message_id"] == "late-receipt"


async def test_cancel_while_waiting_for_transport_never_starts_send(tmp_path):
    sent = []
    owner = ChannelSequenceOwner()

    async def request(req):
        sent.append(req)
        return httpx.Response(200, json={"id": "unexpected"})

    async with transport(request) as bus:
        await bus.transport_lock.acquire()
        task = asyncio.create_task(batch(SessionManager(tmp_path), bus, owner))
        for _ in range(100):
            if bus.has_pending_outbound("qqbot", "c2c:app:a", "incoming-a"):
                break
            await asyncio.sleep(0)
        assert bus.has_pending_outbound("qqbot", "c2c:app:a", "incoming-a")
        owner.stop()
        with pytest.raises(asyncio.CancelledError):
            await asyncio.wait_for(task, 1)
        bus.transport_lock.release()
        await bus.drain_outbound()
    assert sent == []
    rows = SessionManager(tmp_path).get_or_create("role:mira").messages
    assert rows[-1]["delivery_status"] == "failed"


async def test_same_role_other_chat_advances_during_pause_without_stale_tail_loss(
    tmp_path, monkeypatch
):
    pausing, resume = asyncio.Event(), asyncio.Event()
    sent = []
    manager = SessionManager(tmp_path)
    role = RoleStore(tmp_path).create_role(
        role_id="mira", name="Mira", system_prompt="test"
    )
    runtime = RoleRuntime(role)

    async def pause(_):
        pausing.set()
        await resume.wait()

    monkeypatch.setattr("agent.turns.reply_sequence.wait_between_messages", pause)

    async def request(req):
        sent.append(json.loads(req.content)["markdown"]["content"])
        return httpx.Response(200, json={"id": str(len(sent))})

    def context(chat):
        return RoleExecutionContext.create(
            role=role,
            thread_id=chat,
            transport_channel="qqbot",
            transport_chat_id=chat,
            source="channel",
            work_kind="passive_turn",
        )

    async with transport(request) as bus:
        owner = ChannelSequenceOwner()
        first = asyncio.create_task(
            runtime.execute_thread(
                context("a"),
                lambda: batch(
                    manager,
                    bus,
                    owner,
                    texts=("a1", "a2"),
                    state={
                        "pending_messages": True,
                        "expected_mood_updated_at": "",
                        "metadata_updates": {
                            "current_mood": "old",
                            "current_mood_updated_at": "old",
                        },
                    },
                ),
            )
        )
        await asyncio.wait_for(pausing.wait(), 1)
        assert not bus.transport_lock.locked()
        await asyncio.wait_for(
            runtime.execute_thread(
                context("b"),
                lambda: batch(
                    manager,
                    bus,
                    owner,
                    chat="b",
                    texts=("b1",),
                    state={
                        "pending_messages": True,
                        "expected_mood_updated_at": "",
                        "metadata_updates": {
                            "current_mood": "new",
                            "current_mood_updated_at": "new",
                        },
                    },
                ),
            ),
            1,
        )
        resume.set()
        await first
    session = SessionManager(tmp_path).get_or_create("role:mira")
    assert sent == ["a1", "b1", "a2"]
    assert session.metadata["current_mood"] == "new"
    assert all(
        m["delivery_status"] == "sent"
        for m in session.messages
        if m["role"] == "assistant"
    )
