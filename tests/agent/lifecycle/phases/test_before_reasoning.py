from __future__ import annotations

from datetime import datetime
from types import SimpleNamespace
from typing import Any, cast
from unittest.mock import Mock

import pytest

from agent.context import ContextBuilder
from agent.core.types import ContextBundle
from agent.lifecycle.phase import Phase
from agent.lifecycle.phases.before_reasoning import (
    BeforeReasoningFrame,
    default_before_reasoning_modules,
)
from agent.lifecycle.types import BeforeReasoningInput, BeforeTurnCtx, TurnState
from agent.tools.registry import ToolRegistry
from bus.event_bus import EventBus
from bus.events import InboundMessage
from session.manager import Session


@pytest.mark.asyncio
async def test_before_reasoning_syncs_session_key_and_role_id_into_tool_context() -> None:
    bus = EventBus()
    tools = Mock(spec=ToolRegistry)
    session_manager = SimpleNamespace(
        peek_next_message_id=lambda session_key: f"{session_key}:1"
    )
    context_builder = Mock(spec=ContextBuilder)
    context_builder.render = Mock(return_value=ContextBundle())
    phase = Phase(
        default_before_reasoning_modules(
            bus,
            cast(ToolRegistry, tools),
            cast(Any, session_manager),
            cast(ContextBuilder, context_builder),
        ),
        frame_factory=BeforeReasoningFrame,
    )
    session = Session("role:mira")
    session.metadata["role_id"] = "mira"
    timestamp = datetime.now().astimezone()
    message = InboundMessage(
        channel="desktop",
        sender="user",
        chat_id="desktop",
        content="画一张图",
        timestamp=timestamp,
    )
    state = TurnState(msg=message, session_key=session.key, dispatch_outbound=True)
    state.session = session
    before_turn = BeforeTurnCtx(
        session_key=session.key,
        channel="desktop",
        chat_id="desktop",
        content=message.content,
        timestamp=timestamp,
        skill_names=[],
        retrieved_memory_block="",
        retrieval_trace_raw=None,
        history_messages=(),
    )

    await phase.run(BeforeReasoningInput(state=state, before_turn=before_turn))

    tools.set_context.assert_called_once()
    kwargs = tools.set_context.call_args.kwargs
    assert kwargs["session_key"] == "role:mira"
    assert kwargs["role_id"] == "mira"
    assert kwargs["channel"] == "desktop"
    assert kwargs["chat_id"] == "desktop"
