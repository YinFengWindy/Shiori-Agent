from __future__ import annotations

import asyncio
import json
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest

from conversation.service import desktop_thread_id

from agent.core.passive_turn.pipeline import AgentCoreDeps, PassiveTurnPipeline
from agent.core.types import ContextBundle
from agent.lifecycle.types import BeforeReasoningCtx, BeforeTurnCtx
from agent.looping.interrupt import TurnInterruptState
from agent.tools.registry import ToolRegistry
from bus.event_bus import EventBus
from shiori_sdk.messages import InboundMessage
from desktop_bridge.chat_service import DesktopChatService
from session.manager import SessionManager
from session.manager.models import INTERRUPTED_TURN_METADATA_KEY


@pytest.mark.parametrize(
    "mode", ["enabled", "disabled", "cancel", "cancel_before", "malformed"]
)
async def test_complete_messages_are_published_during_turn_and_survive_reload(
    tmp_path, monkeypatch, mode
):
    from agent.core.runtime_support import TurnRunResult
    from agent.turns import reply_sequence
    from core.roles.reply_state import RoleReply
    from shiori_sdk.lifecycle import AfterReasoningCtx
    from shiori_sdk.memory.committed import TurnCommitted
    from agent.turns.reply_sequence import ReplySequencePolicy
    from agent.lifecycle.facade import TurnLifecycle
    from agent.turns.reply_sequence import buffered_reply_scope
    from bootstrap.wiring import wire_turn_lifecycle
    from shiori_sdk.lifecycle import AfterStepCtx
    from agent.core.passive_turn.reasoner import DefaultReasoner
    from agent.core.runtime_support import ToolDiscoveryState
    from agent.core.types import ReasonerResult
    from agent.lifecycle.types import PromptRenderResult
    from agent.looping.ports import LLMConfig, LLMServices
    from agent.core.passive_turn.natural_reply import NaturalReply
    from agent.turns.reply_sequence import ReplySequence

    manager, bus = SessionManager(tmp_path), EventBus()
    session = manager.get_or_create("role:mira")
    session.metadata.update(role_id="mira", current_mood="old")
    session.add_message(
        "user",
        "hi",
        thread_id=desktop_thread_id("mira"),
        metadata={"turn_id": "turn-1"},
    )
    manager.save(session)
    trigger_user_message_id = session.messages[-1]["id"]
    natural = (
        NaturalReply(
            ReplySequence(("one", "two", "three")),
            json.dumps({"messages": ["one", "two", "three"]}),
            ReplySequencePolicy("<host-boundary/>", message_count=3),
        )
        if mode != "disabled"
        else None
    )
    raw = natural.decorated_input if natural else "one\ntwo"
    result = TurnRunResult(
        reply=raw,
        thinking="thinking",
        tools_used=["lookup"],
        role_reply=RoleReply(raw, "new", "我想继续聊"),
        role_reply_mood_fresh=True,
        context_retry={"formal_role_reply": True, "turn_metrics": {"total_tokens": 42}},
        reply_sequence=natural.policy if natural else None,
    )
    summaries = []
    bus.on(TurnCommitted, summaries.append)

    def attach_media(ctx: AfterReasoningCtx):
        ctx.media.append("image.png")
        if mode == "malformed":
            # A decorator dropping validated boundaries must fail before commit.
            ctx.reply = "one"

    bus.on(AfterReasoningCtx, attach_media)
    ready_to_cancel = asyncio.Event()
    interrupt_state = TurnInterruptState(session.key, "hi")
    wire_turn_lifecycle(
        TurnLifecycle(bus), active_turn_states={session.key: interrupt_state}
    )
    tool_preamble = "未发出的工具前正文\n<message-break/>\n尾部"
    tool_chain = [
        {
            "text": tool_preamble,
            "reasoning_content": "tool thinking",
            "calls": [
                {
                    "call_id": "lookup-1",
                    "name": "lookup",
                    "arguments": {},
                    "result": "found",
                    "status": "ok",
                }
            ],
        }
    ]
    default_reasoner = DefaultReasoner(
        llm=LLMServices(provider=AsyncMock(), light_provider=AsyncMock()),
        llm_config=LLMConfig(),
        tools=ToolRegistry(),
        discovery=ToolDiscoveryState(),
        tool_search_enabled=False,
        context=Mock(),
        session_manager=manager,
    )
    default_reasoner.render_prompt = AsyncMock(
        return_value=PromptRenderResult(
            messages=[{"role": "user", "content": "hi"}],
            natural_chat=natural is not None,
        )
    )
    default_reasoner.run = AsyncMock(
        return_value=ReasonerResult(
            reply=raw,
            thinking=result.thinking,
            metadata={
                "tools_used": result.tools_used,
                "tool_chain": tool_chain,
                "role_reply": result.role_reply,
                "role_reply_mood_fresh": True,
                "react_stats": {"total_tokens": 42},
                **({"natural_reply": natural} if natural else {}),
            },
        )
    )

    async def reason(**kwargs):
        if mode == "cancel_before":
            with buffered_reply_scope(True):
                await bus.emit(
                    AfterStepCtx(
                        session_key=session.key,
                        channel="desktop",
                        chat_id=session.key,
                        iteration=1,
                        context_tokens_estimate=0,
                        tools_called=(),
                        partial_reply=raw,
                        tools_used_so_far=(),
                        tool_chain_partial=(),
                        partial_thinking="thinking",
                        has_more=False,
                    )
                )
                ready_to_cancel.set()
                await asyncio.Event().wait()
        return await default_reasoner.run_turn(**kwargs)

    pipeline = PassiveTurnPipeline(
        AgentCoreDeps(
            session=SimpleNamespace(
                session_manager=manager, presence=None, relationship_runtime=None
            ),
            context_store=SimpleNamespace(
                prepare=AsyncMock(return_value=ContextBundle())
            ),
            context=SimpleNamespace(
                render=Mock(return_value=SimpleNamespace(system_prompt="", messages=[]))
            ),
            tools=ToolRegistry(),
            reasoner=SimpleNamespace(run_turn=reason),
            event_bus=bus,
        )
    )

    class Loop:
        def request_interrupt(self, *args, **kwargs):
            return SimpleNamespace(
                status="interrupted", message="cancelled", state=interrupt_state
            )

        def discard_interrupt_state(self, *args):
            pass

        async def process_direct(
            self, content, *, session_key, channel, chat_id, metadata, **kwargs
        ):
            outbound = await pipeline.run(
                InboundMessage(
                    channel=channel,
                    chat_id=chat_id,
                    sender="user",
                    content=content,
                    metadata={
                        **metadata,
                        "omit_user_turn": True,
                        "thread_id": desktop_thread_id("mira"),
                    },
                ),
                session_key,
                dispatch_outbound=False,
            )
            return outbound.content

    emitted = []
    pauses = []

    async def pause(seconds):
        if seconds == 0:
            return
        pauses.append(seconds)
        if mode == "cancel":
            ready_to_cancel.set()
            await asyncio.Event().wait()

    # Replace the owning pause hook, not asyncio's shared module function.
    monkeypatch.setattr(reply_sequence, "wait_between_messages", pause)

    async def emit_payload(emit, event):
        value = emit(event)
        if value is not None:
            await value

    async def emit_session_updated(*, request_id, session, emit_event, messages=None):
        await emit_payload(
            emit_event,
            {
                "id": request_id,
                "method": "session.updated",
                "payload": {
                    "session_key": session.key,
                    "messages": list(messages or []),
                },
            },
        )

    service = DesktopChatService(
        agent_loop=Loop(),
        event_bus=bus,
        session_manager=manager,
        role_id_from_session_key=lambda _: "mira",
        sync_desktop_session_thread=lambda *args, **kwargs: None,
        emit_payload=emit_payload,
        emit_session_updated=emit_session_updated,
    )

    def collect(event):
        if event["method"] == "chat.message":
            assert service.is_busy(session.key)
        emitted.append(event)

    service.start_chat_turn(
        request_id="req",
        session_key=session.key,
        content="hi",
        media=[],
        metadata={
            "turn_id": "turn-1",
            "trigger_user_message_id": trigger_user_message_id,
        },
        omit_user_turn=True,
        emit_event=collect,
        turn_id="turn-1",
    )
    if mode in {"cancel", "cancel_before"}:
        await ready_to_cancel.wait()
        cancelled = await service.cancel_chat_turn_async(session.key, "turn-1")
        assert cancelled.status == "interrupted"
    await service.drain()
    stored = SessionManager(tmp_path).get_or_create(session.key)
    replies = [row for row in stored.messages if row["role"] == "assistant"]
    expected = {
        "enabled": ["one", "two", "three"],
        "disabled": ["one\ntwo"],
        "cancel": ["one"],
        "cancel_before": [""],
        "malformed": [],
    }[mode]
    assert [row["content"] for row in replies] == expected
    if mode in {"enabled", "disabled", "cancel"}:
        expected_chain = [
            {**tool_chain[0], "text": tool_preamble if mode == "disabled" else ""}
        ]
        assert replies[0]["tool_chain"] == expected_chain
        assert replies[0]["metadata"]["tool_chain"] == expected_chain
        assert tool_chain[0]["text"] == tool_preamble
    assert len({row["id"] for row in replies}) == len(expected)
    assert sum(bool(row.get("media")) for row in replies) == int(
        bool(expected) and mode != "cancel_before"
    )
    assert sum(bool(row.get("reasoning_content")) for row in replies) == int(
        bool(expected)
    )
    assert sum(
        bool(row.get("metadata", {}).get("turn_metrics")) for row in replies
    ) == int(bool(expected) and mode != "cancel_before")
    intermediate = [event for event in emitted if event["method"] == "chat.message"]
    assert len(intermediate) == (
        0 if mode in {"disabled", "malformed", "cancel_before"} else len(expected)
    )
    assert [event["payload"]["messages"][-1]["content"] for event in intermediate] == (
        expected if intermediate else []
    )
    assert [
        event["method"]
        for event in emitted
        if event["method"] in {"chat.done", "chat.cancelled", "chat.error"}
    ] == [
        {
            "enabled": "chat.done",
            "disabled": "chat.done",
            "cancel": "chat.cancelled",
            "cancel_before": "chat.cancelled",
            "malformed": "chat.error",
        }[mode]
    ]
    assert len(summaries) == int(mode in {"enabled", "disabled"})
    if summaries:
        assert "<message-break/>" not in summaries[0].assistant_response
        assert len(summaries[0].extra["committed_message_ids"]) == len(expected)
    if mode in {"cancel", "cancel_before"}:
        assert stored.metadata["current_mood"] == "old"
    if expected:
        undone = await manager.undo_last_turn(session.key)
        assert undone is not None and len(undone.deleted_ids) == len(expected) + 1
    await service.aclose()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "exit_path", ["before_turn", "before_reasoning", "provider_error"]
)
async def test_pipeline_early_exit_emits_one_error_and_releases_desktop_turn(
    tmp_path, exit_path
):
    session_manager = SessionManager(tmp_path)
    event_bus = EventBus()
    reasoner = SimpleNamespace(
        run_turn=AsyncMock(side_effect=RuntimeError("provider down"))
    )
    pipeline = PassiveTurnPipeline(
        AgentCoreDeps(
            session=SimpleNamespace(session_manager=session_manager),
            context_store=SimpleNamespace(
                prepare=AsyncMock(return_value=ContextBundle())
            ),
            context=Mock(),
            tools=ToolRegistry(),
            reasoner=reasoner,
            event_bus=event_bus,
        )
    )

    def abort(ctx):
        ctx.abort = True
        ctx.abort_reply = "This turn was blocked."

    if exit_path != "provider_error":
        event_bus.on(
            BeforeTurnCtx if exit_path == "before_turn" else BeforeReasoningCtx, abort
        )

    class _Loop:
        async def process_direct(
            self, content, *, session_key, channel, chat_id, **_kwargs
        ):
            outbound = await pipeline.run(
                InboundMessage(
                    channel=channel,
                    sender="user",
                    chat_id=chat_id,
                    content=content,
                    metadata={
                        "role_id": "mira",
                        "thread_id": desktop_thread_id("mira"),
                    },
                ),
                session_key,
                dispatch_outbound=False,
            )
            return outbound.content

    emitted = []
    busy_on_terminal = []

    def collect(payload):
        if payload["method"] in {"chat.done", "chat.error"}:
            busy_on_terminal.append(service.is_busy("role:mira"))
        emitted.append(payload)

    async def emit_payload(emit_event, payload):
        result = emit_event(payload)
        if result is not None:
            await result

    async def emit_session_updated(*, request_id, session, emit_event, messages=None):
        await emit_payload(
            emit_event,
            {
                "id": request_id,
                "method": "session.updated",
                "payload": {"session_key": session.key},
            },
        )

    service = DesktopChatService(
        agent_loop=_Loop(),
        event_bus=event_bus,
        session_manager=session_manager,
        role_id_from_session_key=lambda _key: "mira",
        sync_desktop_session_thread=lambda _session, *, role_id: None,
        emit_payload=emit_payload,
        emit_session_updated=emit_session_updated,
    )
    for index in range(2):
        service.start_chat_turn(
            request_id=f"request-{index}",
            turn_id=f"turn-{index}",
            session_key="role:mira",
            content="hello",
            media=[],
            metadata={},
            omit_user_turn=True,
            emit_event=collect,
        )
        await service.drain()

    terminals = [
        event for event in emitted if event["method"] in {"chat.done", "chat.error"}
    ]
    assert [event["method"] for event in terminals] == ["chat.error", "chat.error"]
    assert [event["payload"]["turn_id"] for event in terminals] == ["turn-0", "turn-1"]
    expected = (
        "处理消息时出错，请稍后再试。"
        if exit_path == "provider_error"
        else "This turn was blocked."
    )
    assert all(event["payload"]["message"] == expected for event in terminals)
    assert busy_on_terminal == [False, False]
    assert (
        len([event for event in emitted if event["method"] == "session.updated"]) == 2
    )
    assert [event["method"] for event in emitted] == [
        "session.updated",
        "chat.error",
        "session.updated",
        "chat.error",
    ]
    assert not service.is_busy("role:mira")
    assert session_manager.get_or_create("role:mira").messages == []
    assert SessionManager(tmp_path).get_or_create("role:mira").messages == []
    assert reasoner.run_turn.await_count == (2 if exit_path == "provider_error" else 0)


@pytest.mark.asyncio
async def test_desktop_chat_service_reconciles_persisted_user_before_chat_error(
    tmp_path,
):
    session_manager = SessionManager(tmp_path)
    event_bus = EventBus()
    emitted: list[dict] = []
    session = session_manager.get_or_create("role:mira")
    session.add_message("user", "hi")
    await session_manager.append_messages(session, session.messages[:])

    class _Loop:
        async def process_direct(self, *args, **kwargs):
            raise RuntimeError("boom")

    async def _emit_payload(emit_event, payload: dict):
        result = emit_event(payload)
        if result is not None:
            await result

    async def _emit_session_updated(
        request_id: str,
        session,
        emit_event,
        messages=None,
    ) -> None:
        await _emit_payload(
            emit_event,
            {
                "id": request_id,
                "type": "event",
                "method": "session.updated",
                "payload": {
                    "session_key": session.key,
                    "messages": session.messages[:],
                },
            },
        )

    service = DesktopChatService(
        agent_loop=_Loop(),  # type: ignore[arg-type]
        event_bus=event_bus,
        session_manager=session_manager,
        role_id_from_session_key=lambda key: "mira",
        sync_desktop_session_thread=lambda session, role_id: None,
        emit_payload=_emit_payload,
        emit_session_updated=_emit_session_updated,
    )

    with pytest.raises(RuntimeError, match="boom"):
        await service.run_chat_turn(
            request_id="1",
            session_key="role:mira",
            content="hi",
            media=[],
            metadata=None,
            omit_user_turn=True,
            emit_event=emitted.append,
        )

    assert emitted[0]["method"] == "session.updated"
    persisted = SessionManager(tmp_path).get_or_create("role:mira")
    assert emitted[0]["payload"]["messages"] == persisted.messages
    assert persisted.messages[0]["role"] == "user"
    assert persisted.messages[0]["content"] == "hi"
    assert emitted[1:] == [
        {
            "id": "1",
            "type": "event",
            "method": "chat.error",
            "payload": {
                "session_key": "role:mira",
                "turn_id": "1",
                "message": "这次回复未完成，请重试",
                "detail": "RuntimeError: boom",
            },
        }
    ]


@pytest.mark.asyncio
async def test_cancelled_reply_survives_session_manager_reload(tmp_path):
    session_manager = SessionManager(tmp_path)
    session_key = "role:mira"
    _ = session_manager.get_or_create(session_key)
    started = asyncio.Event()
    state = TurnInterruptState(
        session_key=session_key,
        original_user_message="hello",
        partial_reply="partial answer",
        partial_thinking="retain this reasoning",
        tools_used=["web_search"],
        tool_chain_partial=[{"text": "", "calls": [{"name": "web_search"}]}],
    )

    async def _process_direct(*_args, **_kwargs):
        started.set()
        await asyncio.Event().wait()

    service = DesktopChatService(
        agent_loop=SimpleNamespace(
            process_direct=_process_direct,
            request_interrupt=Mock(
                return_value=SimpleNamespace(
                    status="interrupted",
                    message="cancelled",
                    state=state,
                )
            ),
            discard_interrupt_state=Mock(),
        ),
        event_bus=EventBus(),
        session_manager=session_manager,
        role_id_from_session_key=lambda _key: "mira",
        sync_desktop_session_thread=lambda _session, *, role_id: None,
        emit_payload=lambda _emit, _payload: asyncio.sleep(0),
        emit_session_updated=lambda **_kwargs: asyncio.sleep(0),
    )
    service.start_chat_turn(
        request_id="request-1",
        turn_id="turn-1",
        session_key=session_key,
        content="hello",
        media=[],
        metadata={},
        omit_user_turn=True,
        emit_event=lambda _payload: None,
    )
    await started.wait()

    result = await service.cancel_chat_turn_async(session_key, "turn-1")

    assert result.status == "interrupted"
    reloaded = SessionManager(tmp_path).get_or_create(session_key)
    assert reloaded.metadata[INTERRUPTED_TURN_METADATA_KEY]["turn_id"] == "turn-1"
    assistant = reloaded.messages[-1]
    assert assistant["content"] == "partial answer"
    assert assistant["reasoning_content"] == "retain this reasoning"
    assert assistant["tool_chain"] == state.tool_chain_partial
    assert assistant["metadata"]["interrupted_reply"] is True

    await service.aclose()
