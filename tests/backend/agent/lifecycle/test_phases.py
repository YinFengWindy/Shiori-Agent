from __future__ import annotations

from tests.support.generation_getters import run_in_turn
from dataclasses import replace
from datetime import datetime
from pathlib import Path
from types import MappingProxyType, SimpleNamespace
from typing import Any, cast
from unittest.mock import AsyncMock, Mock

import pytest

from agent.core.turn_events import TurnEvents, core_kernel
from shiori_sdk.commands import CommandInput, CommandRegistry
from shiori_sdk.core.conversation import (
    COMMANDS,
    PromptRendering,
    ReasoningFinished,
    ReasoningStarting,
    StepFinished,
    StepStarting,
    TurnStarting,
)
from shiori_sdk.kernel import Kernel, Veto
from tests.support.tool_calls import kernel_with
from agent.context import ContextBuilder
from agent.core.passive_support import build_context_hint_message
from agent.core.passive_turn import ContextStore
from agent.core.runtime_support import TurnRunResult
from agent.core.types import ContextBundle, HistoryMessage
from agent.tools.registry import ToolRegistry
from bus.event_bus import EventBus
from shiori_sdk.messages import InboundMessage
from core.roles import RoleStore
from agent.lifecycle.types import (
    AfterReasoningInput,
    AfterStepCtx,
    BeforeReasoningInput,
    BeforeStepInput,
    BeforeTurnCtx,
    PromptRenderInput,
    TurnState,
)
from agent.lifecycle.phases.after_reasoning import AfterReasoningPhase
from agent.lifecycle.phases.after_step import AfterStepPhase
from agent.lifecycle.phases.before_reasoning import BeforeReasoningPhase
from agent.lifecycle.phases.before_step import BeforeStepPhase
from agent.lifecycle.phases.before_turn import (
    BeforeTurnPhase,
    MemoryConsolidationFailedError,
)
from agent.lifecycle.phases.prompt_render import PromptRenderPhase
from shiori_sdk.prompting import PromptSectionRender
from conversation.store import ConversationStore
from session.manager import SessionManager

_now = datetime.now()


def _inbound() -> InboundMessage:
    return InboundMessage(
        channel="telegram",
        sender="user",
        chat_id="123",
        content="hello",
        timestamp=_now,
    )


class _DummySession:
    def __init__(self, key: str) -> None:
        self.key = key
        self.messages: list[dict[str, object]] = []
        self.metadata: dict[str, object] = {}
        self.last_consolidated = 0

    def get_history(
        self,
        max_messages: int = 500,
        *,
        start_index: int | None = None,
        include: object = None,
    ) -> list[dict[str, object]]:
        return list(self.messages)

    def add_message(
        self, role: str, content: str, media=None, **kwargs: object
    ) -> None:
        msg: dict[str, object] = {"role": role, "content": content}
        if media:
            msg["media"] = list(media)
        msg.update(kwargs)
        self.messages.append(msg)


# ── BeforeTurn ──


@pytest.mark.asyncio
async def test_before_turn_setup_fills_turn_state():
    bus = EventBus()
    session = _DummySession("telegram:123")

    session_mgr = SimpleNamespace(
        get_or_create=lambda key: session,
    )

    bundle = ContextBundle(
        skill_mentions=["search"],
        retrieved_memory_block="block_text",
        retrieval_trace_raw={"trace": 1},
        history_messages=[HistoryMessage(role="user", content="prev")],
    )
    ctx_store = SimpleNamespace(
        prepare=AsyncMock(return_value=bundle),
    )

    phase = BeforeTurnPhase(
        TurnEvents(bus, core_kernel),
        cast(SessionManager, session_mgr),
        cast(ContextStore, ctx_store),
    )
    msg = _inbound()
    state = TurnState(msg=msg, session_key="telegram:123", dispatch_outbound=True)

    ctx = await phase.run(state)

    assert state.session is session
    assert ctx.skill_names == ["search"]
    assert ctx.channel == "telegram"
    assert ctx.chat_id == "123"
    assert ctx.retrieved_memory_block == "block_text"
    assert ctx.retrieval_trace_raw == {"trace": 1}
    assert ctx.history_messages == (HistoryMessage(role="user", content="prev"),)
    assert ctx.abort is False


@pytest.mark.asyncio
async def test_before_turn_ctx_carries_context_scope_of_turn_thread(tmp_path):
    session = _DummySession("role:mira")
    session.metadata["role_id"] = "mira"
    # An external turn also reads its group's listening records (#539).
    session_mgr = SimpleNamespace(
        get_or_create=lambda key: session,
        workspace=tmp_path,
        conversation_store=ConversationStore(tmp_path / "sessions.db"),
    )
    ctx_store = SimpleNamespace(prepare=AsyncMock(return_value=ContextBundle()))
    phase = BeforeTurnPhase(
        TurnEvents(EventBus(), core_kernel),
        cast(SessionManager, session_mgr),
        cast(ContextStore, ctx_store),
    )
    msg = InboundMessage(
        channel="qq",
        sender="user",
        chat_id="group-1",
        content="hello",
        metadata={"role_id": "mira", "thread_id": "thread:mira:qq:group-1"},
    )

    ctx = await phase.run(
        TurnState(msg=msg, session_key="role:mira", dispatch_outbound=True)
    )

    assert ctx.context_scope == "external"


@pytest.mark.asyncio
async def test_before_turn_binds_message_role_id_to_session_before_context_prepare():
    bus = EventBus()
    session = _DummySession("lme:e47becba:qa")
    saved: list[_DummySession] = []
    session_mgr = SimpleNamespace(
        get_or_create=lambda key: session,
        save=lambda value: saved.append(value),
        workspace=Path("unused"),
    )
    ctx_store = SimpleNamespace(prepare=AsyncMock(return_value=ContextBundle()))
    phase = BeforeTurnPhase(
        TurnEvents(bus, core_kernel),
        cast(SessionManager, session_mgr),
        cast(ContextStore, ctx_store),
    )
    msg = InboundMessage(
        channel="benchmark",
        sender="user",
        chat_id="e47becba",
        content="What degree did I graduate with?",
        metadata={"role_id": "benchmark"},
    )

    await phase.run(
        TurnState(msg=msg, session_key="lme:e47becba:qa", dispatch_outbound=False)
    )

    assert session.metadata["role_id"] == "benchmark"
    assert saved == [session]


@pytest.mark.asyncio
async def test_before_turn_uses_cli_session_override_context():
    bus = EventBus()
    session = _DummySession("telegram:7674283004")
    session_mgr = SimpleNamespace(get_or_create=lambda key: session)
    ctx_store = SimpleNamespace(prepare=AsyncMock(return_value=ContextBundle()))
    phase = BeforeTurnPhase(
        TurnEvents(bus, core_kernel),
        cast(SessionManager, session_mgr),
        cast(ContextStore, ctx_store),
    )
    msg = InboundMessage(
        channel="cli",
        sender="user",
        chat_id="cli-1",
        content="hello",
        timestamp=_now,
        metadata={
            "session_key_override": "telegram:7674283004",
            "context_channel": "telegram",
            "context_chat_id": "7674283004",
        },
    )
    state = TurnState(msg=msg, session_key=msg.session_key, dispatch_outbound=True)

    ctx = await phase.run(state)

    assert state.session is session
    assert ctx.session_key == "telegram:7674283004"
    assert ctx.channel == "telegram"
    assert ctx.chat_id == "7674283004"


@pytest.mark.asyncio
async def test_before_turn_chain_can_abort():
    bus = EventBus()
    session = _DummySession("telegram:123")

    session_mgr = SimpleNamespace(get_or_create=lambda key: session)
    bundle = ContextBundle()
    ctx_store = SimpleNamespace(prepare=AsyncMock(return_value=bundle))

    async def abort_handler(event: TurnStarting) -> Veto:
        return Veto("rate limited")

    kernel = kernel_with(on=((TurnStarting, abort_handler),))
    phase = BeforeTurnPhase(
        TurnEvents(bus, lambda: kernel),
        cast(SessionManager, session_mgr),
        cast(ContextStore, ctx_store),
    )
    msg = _inbound()
    state = TurnState(msg=msg, session_key="telegram:123", dispatch_outbound=True)

    ctx = await phase.run(state)
    assert ctx.abort is True
    assert ctx.abort_reply == "rate limited"


@pytest.mark.asyncio
async def test_before_turn_memory_context_guard_blocks_unconsolidated_tail():
    bus = EventBus()
    session = _DummySession("telegram:123")
    session.messages = [{"role": "user", "content": f"u{i}"} for i in range(30)]
    session.last_consolidated = 0
    session_mgr = SimpleNamespace(get_or_create=lambda key: session)
    ctx_store = SimpleNamespace(prepare=AsyncMock())

    phase = BeforeTurnPhase(
        TurnEvents(bus, core_kernel),
        cast(SessionManager, session_mgr),
        cast(ContextStore, ctx_store),
        keep_count=20,
    )
    msg = _inbound()
    state = TurnState(msg=msg, session_key="telegram:123", dispatch_outbound=True)

    ctx = await phase.run(state)

    assert ctx.abort is True
    assert "记忆归档现在处于异常积压状态" in ctx.abort_reply
    assert "当前未归档消息数 30" in ctx.abort_reply
    assert "安全阈值 30" in ctx.abort_reply
    assert "热上下文保留 20" in ctx.abort_reply
    assert "last_consolidated=0" in ctx.abort_reply
    assert "total_messages=30" in ctx.abort_reply
    assert ctx.extra_metadata["memory_context_guard"] == {
        "pending": 30,
        "threshold": 30,
        "keep_count": 20,
        "last_consolidated": 0,
        "total_messages": 30,
    }
    ctx_store.prepare.assert_not_called()


@pytest.mark.asyncio
async def test_before_turn_memory_context_guard_counts_only_the_turn_context(tmp_path):
    """群里积压再多，桌面回合只按用户上下文自己的游标算积压（#523）。"""
    from conversation.service import desktop_thread_id
    from shiori_sdk.channels.threads import network_thread_id

    session = _DummySession("role:mira")
    session.metadata["role_id"] = "mira"
    group = network_thread_id("mira", "qq", "g1")
    session.messages = [
        {"role": "user", "content": f"g{i}", "thread_id": group} for i in range(30)
    ]
    session.messages.append(
        {"role": "user", "content": "hi", "thread_id": desktop_thread_id("mira")}
    )
    session_mgr = SimpleNamespace(get_or_create=lambda key: session, workspace=tmp_path)
    ctx_store = SimpleNamespace(prepare=AsyncMock(return_value=ContextBundle()))
    phase = BeforeTurnPhase(
        TurnEvents(EventBus(), core_kernel),
        cast(SessionManager, session_mgr),
        cast(ContextStore, ctx_store),
        keep_count=20,
    )
    msg = InboundMessage(
        channel="desktop",
        sender="user",
        chat_id="mira",
        content="hello",
        metadata={"role_id": "mira", "thread_id": desktop_thread_id("mira")},
    )

    ctx = await phase.run(
        TurnState(msg=msg, session_key="role:mira", dispatch_outbound=True)
    )

    assert ctx.context_scope == "user"
    assert ctx.abort is False
    ctx_store.prepare.assert_awaited_once()


@pytest.mark.asyncio
async def test_before_turn_memory_context_guard_schedules_consolidation_without_blocking():
    bus = EventBus()
    session = _DummySession("telegram:123")
    session.messages = [{"role": "user", "content": f"u{i}"} for i in range(30)]
    session.last_consolidated = 0
    session_mgr = SimpleNamespace(get_or_create=lambda key: session)
    ctx_store = SimpleNamespace(
        prepare=AsyncMock(return_value=ContextBundle(history_messages=[]))
    )

    class _Consolidator:
        def __init__(self) -> None:
            self.requested: list[str] = []

        def request_memory_consolidation(self, session_key: str) -> None:
            assert session_key == "telegram:123"
            self.requested.append(session_key)

        def get_memory_consolidation_failure(self, session_key: str) -> str | None:
            assert session_key == "telegram:123"
            return None

    consolidator = _Consolidator()

    phase = BeforeTurnPhase(
        TurnEvents(bus, core_kernel),
        cast(SessionManager, session_mgr),
        cast(ContextStore, ctx_store),
        keep_count=20,
        consolidator=consolidator,
    )
    msg = _inbound()
    state = TurnState(msg=msg, session_key="telegram:123", dispatch_outbound=True)

    ctx = await phase.run(state)

    assert ctx.abort is False
    assert session.last_consolidated == 0
    assert consolidator.requested == ["telegram:123"]
    ctx_store.prepare.assert_awaited_once()


@pytest.mark.asyncio
async def test_before_turn_defers_token_pressure_until_complete_request_is_rendered():
    bus = EventBus()

    class _TokenSession(_DummySession):
        def get_history(
            self,
            max_messages: int = 500,
            *,
            start_index: int | None = None,
            include: object = None,
        ) -> list[dict[str, object]]:
            return list(self.messages[max(0, int(start_index or 0)) :])

    session = _TokenSession("telegram:123")
    session.messages = [{"role": "user", "content": "x" * 600}]
    session_mgr = SimpleNamespace(get_or_create=lambda key: session)
    ctx_store = SimpleNamespace(
        prepare=AsyncMock(return_value=ContextBundle(history_messages=[]))
    )

    class _Consolidator:
        def __init__(self) -> None:
            self.ensure_calls = 0

        def get_memory_consolidation_failure(self, session_key: str) -> str | None:
            return None

        def request_memory_consolidation(self, session_key: str) -> None:
            raise AssertionError("token pressure must use awaited consolidation")

    consolidator = _Consolidator()
    phase = BeforeTurnPhase(
        TurnEvents(bus, core_kernel),
        cast(SessionManager, session_mgr),
        cast(ContextStore, ctx_store),
        keep_count=20,
        consolidator=cast(Any, consolidator),
    )

    ctx = await phase.run(
        TurnState(msg=_inbound(), session_key="telegram:123", dispatch_outbound=True)
    )

    assert ctx.abort is False
    assert consolidator.ensure_calls == 0
    ctx_store.prepare.assert_awaited_once()


@pytest.mark.asyncio
async def test_before_turn_memory_context_guard_blocks_after_consolidation_failure():
    bus = EventBus()
    session = _DummySession("telegram:123")
    session.messages = [{"role": "user", "content": f"u{i}"} for i in range(30)]
    session.last_consolidated = 0
    session_mgr = SimpleNamespace(get_or_create=lambda key: session)
    ctx_store = SimpleNamespace(prepare=AsyncMock())

    class _Consolidator:
        def request_memory_consolidation(self, session_key: str) -> None:
            raise AssertionError("failed consolidation must not be rescheduled")

        def get_memory_consolidation_failure(self, session_key: str) -> str | None:
            return "provider timeout"

    phase = BeforeTurnPhase(
        TurnEvents(bus, core_kernel),
        cast(SessionManager, session_mgr),
        cast(ContextStore, ctx_store),
        keep_count=20,
        consolidator=_Consolidator(),
    )
    msg = _inbound()
    state = TurnState(msg=msg, session_key="telegram:123", dispatch_outbound=True)

    with pytest.raises(
        MemoryConsolidationFailedError,
        match="记忆整理失败.*provider timeout",
    ):
        await phase.run(state)
    ctx_store.prepare.assert_not_called()


@pytest.mark.asyncio
async def test_before_turn_memory_context_guard_reports_failure_for_nsfw_role():
    bus = EventBus()
    session = _DummySession("telegram:123")
    session.messages = [{"role": "user", "content": f"u{i}"} for i in range(30)]
    session.last_consolidated = 0
    session.metadata["role_runtime_config"] = {"nsfw_memory_enabled": True}
    session_mgr = SimpleNamespace(get_or_create=lambda key: session)
    ctx_store = SimpleNamespace(
        prepare=AsyncMock(return_value=ContextBundle(history_messages=[]))
    )

    class _Consolidator:
        def request_memory_consolidation(self, session_key: str) -> None:
            raise AssertionError("failed consolidation must not be rescheduled")

        def get_memory_consolidation_failure(self, session_key: str) -> str | None:
            return "invalid response"

    phase = BeforeTurnPhase(
        TurnEvents(bus, core_kernel),
        cast(SessionManager, session_mgr),
        cast(ContextStore, ctx_store),
        keep_count=20,
        consolidator=_Consolidator(),
    )
    msg = _inbound()
    state = TurnState(msg=msg, session_key="telegram:123", dispatch_outbound=True)

    with pytest.raises(MemoryConsolidationFailedError, match="invalid response"):
        await phase.run(state)
    ctx_store.prepare.assert_not_called()


@pytest.mark.asyncio
async def test_before_turn_chain_can_modify_skill_names():
    bus = EventBus()
    session = _DummySession("telegram:123")

    session_mgr = SimpleNamespace(get_or_create=lambda key: session)
    bundle = ContextBundle(skill_mentions=["search"])
    ctx_store = SimpleNamespace(prepare=AsyncMock(return_value=bundle))

    async def add_skill(event: TurnStarting) -> TurnStarting:
        return replace(
            event,
            skill_names=(*event.skill_names, "added_skill"),
            extra_hints=("plugin hint",),
            extra_metadata=MappingProxyType({"plugin_flag": True}),
        )

    kernel = kernel_with(on=((TurnStarting, add_skill),))
    phase = BeforeTurnPhase(
        TurnEvents(bus, lambda: kernel),
        cast(SessionManager, session_mgr),
        cast(ContextStore, ctx_store),
    )
    msg = _inbound()
    state = TurnState(msg=msg, session_key="telegram:123", dispatch_outbound=True)

    ctx = await phase.run(state)
    assert ctx.skill_names == ["search", "added_skill"]
    assert ctx.extra_hints == ["plugin hint"]
    assert ctx.extra_metadata == {"plugin_flag": True}


# ── BeforeReasoning ──


@pytest.mark.asyncio
async def test_before_reasoning_setup_calls_tools_set_context():
    bus = EventBus()
    tools = Mock()
    tools.set_context = Mock()

    session = _DummySession("telegram:123")
    session.messages.append({"role": "user", "content": "prev", "id": "msg_42"})
    session_mgr = SimpleNamespace(get_or_create=lambda key: session)

    context_builder = Mock()
    context_builder.render = Mock(return_value=None)

    phase = BeforeReasoningPhase(
        TurnEvents(bus, core_kernel),
        cast(ToolRegistry, tools),
        cast(SessionManager, session_mgr),
        cast(ContextBuilder, context_builder),
    )
    msg = _inbound()

    before_turn = BeforeTurnCtx(
        session_key="telegram:123",
        channel=msg.channel,
        chat_id=msg.chat_id,
        content=msg.content,
        timestamp=msg.timestamp,
        retrieved_memory_block="block",
        retrieval_trace_raw=None,
        history_messages=(),
        context_scope=None,
        skill_names=["search"],
    )

    state = TurnState(msg=msg, session_key="telegram:123", dispatch_outbound=True)
    state.session = session

    ctx = await phase.run(BeforeReasoningInput(state=state, before_turn=before_turn))

    tools.set_context.assert_called_once()
    call_kwargs = tools.set_context.call_args[1]
    assert call_kwargs["channel"] == "telegram"
    assert call_kwargs["chat_id"] == "123"
    assert call_kwargs["current_user_message"] == msg.content
    assert "current_user_source_ref" in call_kwargs

    assert ctx.skill_names == ["search"]
    assert ctx.retrieved_memory_block == "block"
    assert ctx.extra_hints == []


@pytest.mark.asyncio
async def test_before_reasoning_requires_session():
    bus = EventBus()
    tools = Mock()
    session_mgr = Mock()
    context_builder = Mock()

    phase = BeforeReasoningPhase(
        TurnEvents(bus, core_kernel),
        cast(ToolRegistry, tools),
        cast(SessionManager, session_mgr),
        cast(ContextBuilder, context_builder),
    )
    msg = _inbound()

    before_turn = BeforeTurnCtx(
        session_key="telegram:123",
        channel=msg.channel,
        chat_id=msg.chat_id,
        content=msg.content,
        timestamp=msg.timestamp,
        retrieved_memory_block="",
        retrieval_trace_raw=None,
        history_messages=(),
        context_scope=None,
    )

    state = TurnState(msg=msg, session_key="telegram:123", dispatch_outbound=True)
    # session is None

    with pytest.raises(
        RuntimeError, match="BeforeReasoning requires TurnState.session"
    ):
        await phase.run(BeforeReasoningInput(state=state, before_turn=before_turn))


@pytest.mark.asyncio
async def test_before_reasoning_finalize_calls_render():
    bus = EventBus()
    tools = Mock()
    tools.set_context = Mock()

    session = _DummySession("telegram:123")
    session.my_meta = {"a": 1}
    session_mgr = SimpleNamespace(get_or_create=lambda key: session)
    session_mgr.peek_next_message_id = None

    context_builder = Mock()
    context_builder.render = Mock(return_value=None)

    phase = BeforeReasoningPhase(
        TurnEvents(bus, core_kernel),
        cast(ToolRegistry, tools),
        cast(SessionManager, session_mgr),
        cast(ContextBuilder, context_builder),
    )
    msg = _inbound()

    before_turn = BeforeTurnCtx(
        session_key="telegram:123",
        channel=msg.channel,
        chat_id=msg.chat_id,
        content=msg.content,
        timestamp=msg.timestamp,
        retrieved_memory_block="block",
        retrieval_trace_raw=None,
        history_messages=(),
        context_scope=None,
        skill_names=["search"],
    )

    state = TurnState(msg=msg, session_key="telegram:123", dispatch_outbound=True)
    state.session = session

    await phase.run(BeforeReasoningInput(state=state, before_turn=before_turn))

    context_builder.render.assert_called_once()
    call_args = context_builder.render.call_args[0][0]
    assert call_args.skill_names == ["search"]
    assert call_args.retrieved_memory_block == "block"
    assert call_args.channel == msg.channel
    assert call_args.chat_id == msg.chat_id


@pytest.mark.asyncio
async def test_before_reasoning_chain_can_add_extra_hints():
    bus = EventBus()
    tools = Mock()
    tools.set_context = Mock()

    session = _DummySession("telegram:123")
    session_mgr = SimpleNamespace(get_or_create=lambda key: session)

    context_builder = Mock()
    context_builder.render = Mock(return_value=None)

    async def hint_handler(event: ReasoningStarting) -> ReasoningStarting:
        return replace(event, extra_hints=(*event.extra_hints, "hint from plugin"))

    kernel = kernel_with(on=((ReasoningStarting, hint_handler),))
    phase = BeforeReasoningPhase(
        TurnEvents(bus, lambda: kernel),
        cast(ToolRegistry, tools),
        cast(SessionManager, session_mgr),
        cast(ContextBuilder, context_builder),
    )
    msg = _inbound()

    before_turn = BeforeTurnCtx(
        session_key="telegram:123",
        channel=msg.channel,
        chat_id=msg.chat_id,
        content=msg.content,
        timestamp=msg.timestamp,
        retrieved_memory_block="",
        retrieval_trace_raw=None,
        history_messages=(),
        context_scope=None,
        extra_hints=["hint from before turn"],
    )

    state = TurnState(msg=msg, session_key="telegram:123", dispatch_outbound=True)
    state.session = session

    ctx = await phase.run(BeforeReasoningInput(state=state, before_turn=before_turn))
    assert ctx.extra_hints == ["hint from before turn", "hint from plugin"]


@pytest.mark.asyncio
async def test_before_reasoning_chain_modify_skill_names_used_in_finalize_render():
    bus = EventBus()
    tools = Mock()
    tools.set_context = Mock()

    session = _DummySession("telegram:123")
    session_mgr = SimpleNamespace(get_or_create=lambda key: session)

    context_builder = Mock()
    context_builder.render = Mock(return_value=None)

    async def modify_chain(event: ReasoningStarting) -> ReasoningStarting:
        return replace(
            event,
            skill_names=(*event.skill_names, "chain_added_skill"),
            retrieved_memory_block="chain_modified_block",
        )

    kernel = kernel_with(on=((ReasoningStarting, modify_chain),))
    phase = BeforeReasoningPhase(
        TurnEvents(bus, lambda: kernel),
        cast(ToolRegistry, tools),
        cast(SessionManager, session_mgr),
        cast(ContextBuilder, context_builder),
    )
    msg = _inbound()

    before_turn = BeforeTurnCtx(
        session_key="telegram:123",
        channel=msg.channel,
        chat_id=msg.chat_id,
        content=msg.content,
        timestamp=msg.timestamp,
        retrieved_memory_block="original_block",
        retrieval_trace_raw=None,
        history_messages=(),
        context_scope=None,
        skill_names=["base_skill"],
    )

    state = TurnState(msg=msg, session_key="telegram:123", dispatch_outbound=True)
    state.session = session

    _ = await phase.run(BeforeReasoningInput(state=state, before_turn=before_turn))

    # finalize 必须用 chain 修改后的值 render
    call_args = context_builder.render.call_args[0][0]
    assert "chain_added_skill" in call_args.skill_names
    assert call_args.retrieved_memory_block == "chain_modified_block"


@pytest.mark.asyncio
async def test_before_step_setup_records_token_estimate():
    bus = EventBus()
    phase = BeforeStepPhase(TurnEvents(bus, core_kernel))
    messages = [{"role": "user", "content": "hello"}]

    ctx = await phase.run(
        BeforeStepInput(
            session_key="k",
            channel="c",
            chat_id="ch",
            iteration=1,
            messages=messages,
            visible_names=None,
        )
    )

    assert ctx.input_tokens_estimate > 0


@pytest.mark.asyncio
async def test_prompt_render_chain_respects_disabled_sections(tmp_path):
    RoleStore(tmp_path).create_role(role_id="mira", name="Mira", system_prompt="test")

    async def add_bottom(event: PromptRendering) -> PromptRendering:
        section = PromptSectionRender(
            name="memes", content="# Memes\n\n<meme:happy>", is_static=False
        )
        return replace(event, system_sections_bottom=(section,))

    kernel = kernel_with(on=((PromptRendering, add_bottom),))
    memory = SimpleNamespace(
        read_self=lambda: "",
        read_profile=lambda: "",
        read_recent_context=lambda: "",
        get_memory_context=lambda: "",
    )
    context = ContextBuilder(
        tmp_path, memory=cast(Any, memory), runtime_roles=RoleStore(tmp_path)
    )
    phase = run_in_turn(
        PromptRenderPhase(TurnEvents(EventBus(), lambda: kernel), context)
    )

    result = await phase.run(
        PromptRenderInput(
            session_key="k",
            channel="cli",
            chat_id="ch",
            content="hello",
            media=None,
            timestamp=_now,
            history=[],
            skill_names=None,
            retrieved_memory_block="",
            disabled_sections={"memes"},
            turn_injection_prompt="",
            session_metadata={"role_id": "mira"},
        )
    )

    assert "<meme:happy>" not in str(result.messages[0]["content"])


@pytest.mark.asyncio
async def test_before_step_finalize_injects_extra_hints():
    bus = EventBus()

    async def append_hint(event: StepStarting) -> StepStarting:
        return replace(event, extra_hints=(*event.extra_hints, "hints from plugin"))

    kernel = kernel_with(on=((StepStarting, append_hint),))
    phase = BeforeStepPhase(TurnEvents(bus, lambda: kernel))
    messages = [{"role": "user", "content": "hello"}]

    await phase.run(
        BeforeStepInput(
            session_key="k",
            channel="c",
            chat_id="ch",
            iteration=1,
            messages=messages,
            visible_names=None,
        )
    )

    expected = build_context_hint_message("plugin_hints", "hints from plugin")
    assert messages == [{"role": "user", "content": "hello"}, expected]


@pytest.mark.asyncio
async def test_before_step_finalize_early_stop():
    bus = EventBus()

    async def stop_early(event: StepStarting) -> Veto:
        return Veto("预算不足")

    kernel = kernel_with(on=((StepStarting, stop_early),))
    phase = BeforeStepPhase(TurnEvents(bus, lambda: kernel))
    messages = [{"role": "user", "content": "hello"}]

    ctx = await phase.run(
        BeforeStepInput(
            session_key="k",
            channel="c",
            chat_id="ch",
            iteration=1,
            messages=messages,
            visible_names=None,
        )
    )

    assert ctx.early_stop is True
    assert ctx.early_stop_reply == "预算不足"


@pytest.mark.asyncio
async def test_after_step_phase_runs_observers():
    bus = EventBus()
    side_effect: list[str] = []

    async def handler(event: StepFinished) -> None:
        side_effect.append(event.partial_reply)

    bus.on(StepFinished, handler)
    phase = AfterStepPhase(TurnEvents(bus, core_kernel))
    await phase.run(
        AfterStepCtx(
            session_key="k",
            channel="c",
            chat_id="ch",
            iteration=0,
            context_tokens_estimate=0,
            tools_called=(),
            partial_reply="ok",
            tools_used_so_far=(),
            tool_chain_partial=(),
            partial_thinking=None,
            has_more=True,
        )
    )

    assert side_effect == ["ok"]


@pytest.mark.asyncio
async def test_after_reasoning_applies_reasoning_finished_to_store_and_outbound():
    async def attach(event: ReasoningFinished) -> ReasoningFinished:
        return replace(
            event,
            media=("/tmp/a.png",),
            outbound_metadata=MappingProxyType(
                {**event.outbound_metadata, "plugin_flag": "m"}
            ),
        )

    kernel = kernel_with(on=((ReasoningFinished, attach),))
    session = _DummySession("telegram:123")
    msg = _inbound()
    state = TurnState(msg=msg, session_key=session.key, dispatch_outbound=True)
    state.session = session
    state.extra_metadata["before_turn_flag"] = "bt"
    services = SimpleNamespace(
        presence=Mock(),
        session_manager=SimpleNamespace(append_messages=AsyncMock()),
    )
    turn_result = TurnRunResult(
        reply="reply",
        tool_chain=[],
        tools_used=[],
        thinking=None,
        streamed=False,
        context_retry={},
    )
    phase = AfterReasoningPhase(
        EventBus(),
        TurnEvents(EventBus(), lambda: kernel),
        cast(Any, services),
    )
    run_in_turn(phase, method="run")

    result = await phase.run(AfterReasoningInput(state=state, turn_result=turn_result))

    assert session.messages[1]["media"] == ["/tmp/a.png"]
    assert result.outbound.metadata["before_turn_flag"] == "bt"
    assert result.outbound.metadata["plugin_flag"] == "m"
    assert result.outbound.media == ["/tmp/a.png"]


@pytest.mark.asyncio
async def test_after_reasoning_carries_the_persisted_assistant_message_id_into_outbound(
    tmp_path: Path,
):
    """Pins the load-bearing assumption behind #305's fix: after append_messages

    actually commits the assistant reply, the outbound message it builds must
    carry that exact row's id as ``committed_message_id``. Without this, every
    delivery mark silently stops writing anywhere (mark_delivery treats a
    missing id as "nothing to mark" and returns None) — a regression that
    produces no error and fails no assertion unless something checks for the
    id explicitly.

    Uses a real SessionManager/SQLite store (not a mock) so the assertion
    exercises the actual id-assignment mutation in
    ``_persist_messages``/``msg.update(row)``, not a stand-in.
    """
    session_manager = SessionManager(tmp_path)
    session_key = "telegram:123"
    session = session_manager.get_or_create(session_key)
    msg = _inbound()
    state = TurnState(msg=msg, session_key=session_key, dispatch_outbound=True)
    state.session = session
    services = SimpleNamespace(
        presence=None,
        session_manager=session_manager,
    )
    turn_result = TurnRunResult(
        reply="reply",
        tool_chain=[],
        tools_used=[],
        thinking=None,
        streamed=False,
        context_retry={},
    )
    phase = run_in_turn(
        AfterReasoningPhase(
            EventBus(), TurnEvents(EventBus(), core_kernel), cast(Any, services)
        )
    )

    result = await phase.run(AfterReasoningInput(state=state, turn_result=turn_result))

    persisted_assistant = next(
        message for message in session.messages if message["role"] == "assistant"
    )
    assert persisted_assistant["id"]
    assert result.outbound.committed_message_id == persisted_assistant["id"]


@pytest.mark.asyncio
async def test_after_reasoning_persists_user_display_content_without_internal_metadata():
    session = _DummySession("desktop:role:mira")
    msg = InboundMessage(
        channel="desktop",
        sender="user",
        chat_id="desktop:role:mira",
        content="【你正在回复一条历史消息】\n被回复消息：\nold\n\n【你当前新消息】\nnew",
        timestamp=_now,
        metadata={
            "persisted_user_content": "new",
            "reply_to_message_id": "message-1",
            "reply_to_content": "old",
        },
    )
    state = TurnState(msg=msg, session_key=session.key, dispatch_outbound=True)
    state.session = session
    services = SimpleNamespace(
        presence=Mock(),
        session_manager=SimpleNamespace(append_messages=AsyncMock()),
    )
    turn_result = TurnRunResult(
        reply="reply",
        tool_chain=[],
        tools_used=[],
        thinking=None,
        streamed=False,
        context_retry={},
    )
    phase = run_in_turn(
        AfterReasoningPhase(
            EventBus(), TurnEvents(EventBus(), core_kernel), cast(Any, services)
        )
    )

    await phase.run(AfterReasoningInput(state=state, turn_result=turn_result))

    assert session.messages[0]["content"] == "new"
    metadata = cast(dict[str, object], session.messages[0]["metadata"])
    assert metadata["reply_to_message_id"] == "message-1"
    assert metadata["reply_to_content"] == "old"
    assert "persisted_user_content" not in metadata


@pytest.mark.asyncio
async def test_after_reasoning_copies_thread_id_into_persisted_messages():
    session = _DummySession("role:mira")
    session.metadata["thread_id"] = "thread:mira:telegram:123"
    msg = InboundMessage(
        channel="telegram",
        sender="user",
        chat_id="123",
        content="hi",
        timestamp=_now,
        metadata={
            "role_id": "mira",
            "thread_id": "thread:mira:telegram:123",
            "transport_channel": "telegram",
            "transport_chat_id": "123",
        },
    )
    state = TurnState(msg=msg, session_key=session.key, dispatch_outbound=True)
    state.session = session
    services = SimpleNamespace(
        presence=Mock(),
        session_manager=SimpleNamespace(append_messages=AsyncMock()),
    )
    turn_result = TurnRunResult(
        reply="reply",
        tool_chain=[],
        tools_used=[],
        thinking=None,
        streamed=False,
        context_retry={},
    )
    phase = run_in_turn(
        AfterReasoningPhase(
            EventBus(), TurnEvents(EventBus(), core_kernel), cast(Any, services)
        )
    )

    await phase.run(AfterReasoningInput(state=state, turn_result=turn_result))

    assert session.messages[0]["thread_id"] == "thread:mira:telegram:123"
    assert session.messages[1]["thread_id"] == "thread:mira:telegram:123"


class _RecordingConsolidator:
    """Records which consolidation the context guard asked for."""

    def __init__(self) -> None:
        self.requested: list[str] = []
        self.ensured: list[str] = []

    def request_memory_consolidation(self, session_key: str) -> None:
        self.requested.append(session_key)

    def get_memory_consolidation_failure(self, session_key: str) -> str | None:
        return None


async def _guard_group_turn(
    manager: SessionManager, consolidator: _RecordingConsolidator, **guard: Any
) -> None:
    phase = BeforeTurnPhase(
        TurnEvents(EventBus(), core_kernel),
        manager,
        cast(
            ContextStore,
            SimpleNamespace(prepare=AsyncMock(return_value=ContextBundle())),
        ),
        consolidator=cast(Any, consolidator),
        **guard,
    )
    msg = InboundMessage(
        channel="qq",
        sender="77",
        chat_id="gqq:2",
        content="hello",
        metadata={"role_id": "mira", "thread_id": "thread:mira:qq:gqq:2"},
    )
    await phase.run(TurnState(msg=msg, session_key="role:mira", dispatch_outbound=True))


@pytest.mark.asyncio
async def test_backlog_counts_the_whole_external_context(tmp_path: Path) -> None:
    """The external cursor is shared, so other groups' backlog triggers it (#539)."""
    manager = SessionManager(tmp_path)
    session = manager.get_or_create("role:mira")
    session.metadata["role_id"] = "mira"
    for index in range(20):
        session.add_message("user", f"a{index}", thread_id="thread:mira:qq:gqq:1")
        session.add_message("assistant", "ok", thread_id="thread:mira:qq:gqq:1")
    manager.save(session)
    consolidator = _RecordingConsolidator()

    await _guard_group_turn(manager, consolidator, keep_count=20)

    assert consolidator.requested == ["role:mira"]


@pytest.mark.asyncio
async def test_before_turn_leaves_listening_budget_to_complete_request_preflight(
    tmp_path: Path,
) -> None:
    manager = SessionManager(tmp_path)
    session = manager.get_or_create("role:mira")
    session.metadata["role_id"] = "mira"
    manager.save(session)
    consolidator = _RecordingConsolidator()
    await _guard_group_turn(manager, consolidator)
    assert consolidator.ensured == []

    listening = manager.conversation_store.listening
    listening.switches.set_enabled("thread:mira:qq:gqq:2", True, operator="user")
    for index in range(30):
        listening.hear(
            "thread:mira:qq:gqq:2",
            sender_id="77",
            content="闲" * 80,
            source={"sender_name": "阿花"},
            external_message_id=f"m{index}",
            timestamp=datetime.now().astimezone(),
        )
    # Partial history cannot decide the final model budget, including listening.
    await _guard_group_turn(manager, consolidator)
    assert consolidator.ensured == []


@pytest.mark.asyncio
async def test_registered_command_answers_before_retrieval_and_keeps_session():
    received: list[CommandInput] = []

    async def example(command: CommandInput) -> str:
        received.append(command)
        return "neutral command reply"

    kernel, commands = Kernel(), CommandRegistry()
    kernel.provide(COMMANDS, commands)
    _ = commands.register("example", example)
    session = _DummySession("telegram:123")
    session.messages = [{"role": "user", "content": "kept"}]
    session.last_consolidated = 1
    context = SimpleNamespace(prepare=AsyncMock())
    phase = BeforeTurnPhase(
        TurnEvents(EventBus(), lambda: kernel),
        cast(SessionManager, SimpleNamespace(get_or_create=lambda key: session)),
        cast(ContextStore, context),
    )
    message = _inbound()
    message.content = "/Example@bot now"
    result = await phase.run(
        TurnState(msg=message, session_key=session.key, dispatch_outbound=True)
    )
    assert result.abort and result.abort_reply == "neutral command reply"
    assert result.channel == message.channel and result.timestamp == message.timestamp
    assert received == [
        CommandInput(
            "/Example@bot now",
            "telegram:123",
            ({"role": "user", "content": "kept"},),
            1,
        )
    ]
    context.prepare.assert_not_called()
    assert len(session.messages) == 1 and session.last_consolidated == 1
