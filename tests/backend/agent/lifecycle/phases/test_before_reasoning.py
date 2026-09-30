from __future__ import annotations

from datetime import datetime
from pathlib import Path
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
from conversation.context_scope import turn_context_view
from conversation.service import network_thread_id
from core.memory.group_environment import GroupEnvironment, GroupEnvironmentUpdate
from core.roles import RoleStore
from session.manager import Session, SessionManager


@pytest.mark.asyncio
async def test_before_reasoning_syncs_session_key_and_role_id_into_tool_context() -> (
    None
):
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
        context_scope=None,
    )

    await phase.run(BeforeReasoningInput(state=state, before_turn=before_turn))

    tools.set_context.assert_called_once()
    kwargs = tools.set_context.call_args.kwargs
    assert kwargs["session_key"] == "role:mira"
    assert kwargs["role_id"] == "mira"
    assert kwargs["channel"] == "desktop"
    assert kwargs["chat_id"] == "desktop"


@pytest.mark.asyncio
async def test_prompt_warmup_renders_external_turn_with_its_group_note(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    class _Memory:
        def read_self(self) -> str:
            return ""

        def read_recent_context(self) -> str:
            return ""

        def get_memory_context(self) -> str:
            return ""

    roles = RoleStore(tmp_path)
    roles.create_role(role_id="mira", name="Mira", system_prompt="test role")
    manager = SessionManager(tmp_path)
    group = network_thread_id("mira", "qq", "g1")
    environment = GroupEnvironment(tmp_path, manager.conversation_store)
    environment.apply(
        "mira",
        GroupEnvironmentUpdate(
            thread_id=group,
            label="群「猫猫群」",
            recent_activity="",
            group_note="## 氛围\n猫猫群的笔记",
        ),
        updated_at=datetime.now().astimezone(),
    )
    builder = ContextBuilder(
        tmp_path, _Memory(), runtime_roles=roles  # type: ignore[arg-type]
    )
    builder.set_group_environment(environment)
    rendered: list[str] = []
    real_render = builder.render

    def spy_render(*args: Any, **kwargs: Any):
        result = real_render(*args, **kwargs)
        rendered.append("\n".join(str(m["content"]) for m in result.messages))
        return result

    monkeypatch.setattr(builder, "render", spy_render)
    tools = Mock(spec=ToolRegistry)
    phase = Phase(
        default_before_reasoning_modules(
            EventBus(),
            cast(ToolRegistry, tools),
            cast(
                Any,
                SimpleNamespace(peek_next_message_id=lambda key: f"{key}:1"),
            ),
            builder,
        ),
        frame_factory=BeforeReasoningFrame,
    )
    session = Session("role:mira")
    session.metadata["role_id"] = "mira"
    timestamp = datetime.now().astimezone()
    message = InboundMessage(
        channel="qq",
        sender="555",
        chat_id="g1",
        content="大家好",
        timestamp=timestamp,
        metadata={"thread_id": group, "role_id": "mira"},
    )
    state = TurnState(msg=message, session_key=session.key, dispatch_outbound=True)
    state.session = session
    state.context_view = turn_context_view(tmp_path, "mira", group)
    before_turn = BeforeTurnCtx(
        session_key=session.key,
        channel="qq",
        chat_id="g1",
        content=message.content,
        timestamp=timestamp,
        skill_names=[],
        retrieved_memory_block="",
        retrieval_trace_raw=None,
        history_messages=(),
        context_scope=state.context_scope,
    )

    await phase.run(BeforeReasoningInput(state=state, before_turn=before_turn))

    assert state.context_scope == "external"
    # 工具按回合身份收窄（#540）：群友触发的外部回合。
    context = tools.set_context.call_args.kwargs
    assert (
        context["sender_id"],
        context["sender_is_user"],
        context["context_scope"],
    ) == ("555", "false", "external")
    [prompt] = rendered
    assert "猫猫群的笔记" in prompt
