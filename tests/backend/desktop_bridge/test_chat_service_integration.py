from __future__ import annotations

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest

from agent.core.passive_turn.pipeline import AgentCoreDeps, PassiveTurnPipeline
from agent.core.types import ContextBundle
from agent.lifecycle.types import BeforeReasoningCtx, BeforeTurnCtx
from agent.looping.interrupt import TurnInterruptState
from agent.tools.registry import ToolRegistry
from bus.event_bus import EventBus
from bus.events import InboundMessage
from desktop_bridge.chat_service import DesktopChatService
from session.manager import SessionManager
from session.manager.models import INTERRUPTED_TURN_METADATA_KEY


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
                    channel=channel, sender="user", chat_id=chat_id, content=content
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

    async def emit_session_updated(*, request_id, session, emit_event):
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
                "message": "boom",
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
