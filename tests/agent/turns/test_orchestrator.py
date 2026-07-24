from __future__ import annotations

from typing import Any, cast
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from agent.looping.ports import SessionServices
from agent.turns.orchestrator import TurnOrchestrator, TurnOrchestratorDeps
from agent.turns.outbound import OutboundDispatch
from agent.turns.result import TurnOutbound, TurnResult
from bus.event_bus import EventBus
from bus.events_lifecycle import ProactiveMessageCommitted


@pytest.mark.asyncio
async def test_proactive_media_commit_notifies_shared_session() -> None:
    session = SimpleNamespace(
        key="role:mira",
        metadata={"role_id": "mira"},
        messages=[],
    )

    def add_message(role: str, content: str, media=None, **kwargs) -> None:
        session.messages.append(
            {
                "role": role,
                "content": content,
                "media": list(media or []),
                **kwargs,
            }
        )

    session.add_message = add_message
    session_manager = SimpleNamespace(
        get_or_create=lambda _key: session,
        append_messages=AsyncMock(return_value=None),
    )

    class _Outbound:
        result = True

        async def dispatch(self, outbound: OutboundDispatch) -> bool:
            return self.result

    event_bus = EventBus()
    committed: list[ProactiveMessageCommitted] = []
    event_bus.on(ProactiveMessageCommitted, committed.append)
    outbound = _Outbound()
    orchestrator = TurnOrchestrator(
        TurnOrchestratorDeps(
            session=SessionServices(
                session_manager=cast(Any, session_manager),
                presence=None,
            ),
            outbound=outbound,
            event_bus=event_bus,
        )
    )

    result = TurnResult(
        decision="reply",
        outbound=TurnOutbound(
            session_key="role:mira",
            content="给你看张图",
            media=["D:\\media\\scene.png"],
        ),
    )
    await orchestrator.handle_proactive_turn(
        result=result,
        session_key="role:mira",
        channel="telegram",
        chat_id="123",
    )

    assert session.messages[0]["media"] == ["D:\\media\\scene.png"]
    assert committed == [
        ProactiveMessageCommitted(
            session_key="role:mira",
            channel="telegram",
            role_id="mira",
            chat_id="123",
            assistant_response="给你看张图",
            tools_used=("message_push",),
        )
    ]

    outbound.result = False
    committed.clear()
    sent = await orchestrator.handle_proactive_turn(
        result=result,
        session_key="role:mira",
        channel="telegram",
        chat_id="123",
    )

    assert sent is False
    assert committed == []


@pytest.mark.asyncio
async def test_proactive_retry_dispatches_without_recommitting_shared_session() -> None:
    session = SimpleNamespace(
        key="role:mira",
        metadata={"role_id": "mira"},
        messages=[],
    )
    session_manager = SimpleNamespace(
        get_or_create=lambda _key: session,
        append_messages=AsyncMock(return_value=None),
    )
    dispatched: list[OutboundDispatch] = []

    class _Outbound:
        async def dispatch(self, outbound: OutboundDispatch) -> bool:
            dispatched.append(outbound)
            return True

    event_bus = EventBus()
    committed: list[ProactiveMessageCommitted] = []
    event_bus.on(ProactiveMessageCommitted, committed.append)
    orchestrator = TurnOrchestrator(
        TurnOrchestratorDeps(
            session=SessionServices(
                session_manager=cast(Any, session_manager),
                presence=None,
            ),
            outbound=_Outbound(),
            event_bus=event_bus,
        )
    )
    result = TurnResult(
        decision="reply",
        outbound=TurnOutbound(
            session_key="role:mira",
            content="跨渠道提醒",
            media=["D:\\media\\scene.png"],
        ),
    )

    sent = await orchestrator.dispatch_proactive_retry(
        result=result,
        session_key="role:mira",
        channel="telegram",
        chat_id="123",
    )

    assert sent is True
    assert len(dispatched) == 1
    assert dispatched[0].channel == "telegram"
    assert dispatched[0].media == ["D:\\media\\scene.png"]
    session_manager.append_messages.assert_not_awaited()
    assert committed == []
