from __future__ import annotations

from dataclasses import replace
from datetime import datetime
from types import SimpleNamespace
from typing import cast
from unittest.mock import AsyncMock, MagicMock

import pytest

from agent.context import ContextBuilder
from agent.core.passive_turn import ContextStore, Reasoner
from agent.core.runtime_support import SessionLike, TurnRunResult
from agent.core.passive_support import predict_current_user_source_ref
from agent.core.passive_turn import AgentCore, AgentCoreDeps
from agent.core.types import ContextBundle
from agent.looping.ports import SessionServices
from agent.tools.registry import ToolRegistry
from agent.turns.outbound import OutboundPort
from bus.event_bus import EventBus
from shiori_sdk.messages import InboundMessage
from shiori_sdk.core.conversation import ReasoningStarting, TurnStarting
from shiori_sdk.kernel import Veto
from tests.support.tool_calls import kernel_with
from agent.lifecycle.phases.before_turn import MemoryConsolidationFailedError
from session.manager import SessionManager


class _DummySession:
    def __init__(self, key: str) -> None:
        self.key = key
        self.messages: list[dict] = []
        self.metadata: dict[str, object] = {}
        self.last_consolidated = 0

    def get_history(
        self,
        max_messages: int = 500,
        *,
        start_index: int | None = None,
        include: object = None,
    ) -> list[dict]:
        if start_index is not None:
            return self.messages[start_index:][-max_messages:]
        return self.messages[-max_messages:]

    def add_message(
        self,
        role: str,
        content: str,
        media=None,
        **kwargs: object,
    ) -> None:
        if media is not None:
            kwargs["media"] = media
        self.messages.append({"role": role, "content": content, **kwargs})


@pytest.mark.asyncio
async def test_agent_core_process_runs_prepare_prompt_run_commit_in_order():
    order: list[str] = []
    session = _DummySession("telegram:123")
    context_store = SimpleNamespace(
        prepare=AsyncMock(
            side_effect=lambda **kwargs: order.append("prepare")
            or ContextBundle(
                skill_mentions=["refactor"],
                retrieved_memory_block="remembered",
                retrieval_trace_raw={"route": "RETRIEVE"},
            )
        )
    )

    def _render(request, *, session_metadata=None):
        _ = request, session_metadata
        order.append("render")
        return SimpleNamespace(system_prompt="system prompt", messages=[])

    context = SimpleNamespace(render=MagicMock(side_effect=_render))
    tools = ToolRegistry()
    tools.set_context = MagicMock(
        side_effect=lambda **kwargs: order.append("tool_context")
    )
    reasoner = SimpleNamespace(
        run_turn=AsyncMock(
            side_effect=lambda *args, **kwargs: order.append("run")
            or TurnRunResult(
                reply="final",
                tools_used=["shell"],
                tool_chain=[{"text": "done", "calls": []}],
                thinking="think",
                context_retry={"selected_plan": "full"},
            )
        ),
    )
    agent_core = AgentCore(
        AgentCoreDeps(
            session=cast(
                SessionServices,
                SimpleNamespace(
                    session_manager=SimpleNamespace(
                        get_or_create=MagicMock(return_value=session),
                        peek_next_message_id=MagicMock(return_value="telegram:123:0"),
                        append_messages=AsyncMock(),
                    ),
                    presence=None,
                ),
            ),
            context_store=cast(ContextStore, context_store),
            context=cast(ContextBuilder, context),
            tools=cast(ToolRegistry, tools),
            reasoner=cast(Reasoner, reasoner),
        )
    )
    msg = InboundMessage(
        channel="telegram",
        sender="hua",
        chat_id="123",
        content="你好",
        timestamp=datetime(2026, 4, 4, 22, 0, 0),
    )

    out = await agent_core.process(msg, "telegram:123")

    assert out.content == "final"
    assert order == ["prepare", "tool_context", "render", "run"]
    assert context_store.prepare.await_args.kwargs["session_key"] == "telegram:123"
    render_request = context.render.call_args.args[0]
    assert render_request.current_message == ""
    assert render_request.skill_names == ["refactor"]
    assert render_request.retrieved_memory_block == "remembered"
    assert context.render.call_args.kwargs["session_metadata"] == {}
    tools.set_context.assert_called_once_with(
        channel="telegram",
        chat_id="123",
        session_key="telegram:123",
        turn_session_key="telegram:123",
        role_id="",
        current_user_message="你好",
        role_config_version="",
        thread_id="",
        delivery_key="",
        sender_id="hua",
        sender_is_user="true",
        account_full_tools="false",
        context_scope="",
        current_user_source_ref="telegram:123:0",
        current_timestamp="2026-04-04T22:00:00",
        defer_push_session_sync="true",
    )
    assert reasoner.run_turn.await_args.kwargs["skill_names"] == ["refactor"]
    assert reasoner.run_turn.await_args.kwargs["retrieved_memory_block"] == "remembered"
    # AfterReasoning persists user+assistant messages to session
    assert len(session.messages) == 2
    assert session.messages[0]["role"] == "user"
    assert session.messages[1]["role"] == "assistant"
    assert session.messages[1]["content"] == "final"


@pytest.mark.asyncio
async def test_agent_core_process_coerces_empty_reply_before_commit():
    session = _DummySession("cli:1")
    context_store = SimpleNamespace(
        prepare=AsyncMock(return_value=ContextBundle()),
    )
    agent_core = AgentCore(
        AgentCoreDeps(
            session=cast(
                SessionServices,
                SimpleNamespace(
                    session_manager=SimpleNamespace(
                        get_or_create=MagicMock(return_value=session),
                        peek_next_message_id=MagicMock(return_value="cli:1:0"),
                        append_messages=AsyncMock(),
                    ),
                    presence=None,
                ),
            ),
            context_store=cast(ContextStore, context_store),
            context=cast(
                ContextBuilder,
                SimpleNamespace(
                    render=MagicMock(
                        return_value=SimpleNamespace(
                            system_prompt="prompt", messages=[]
                        )
                    ),
                ),
            ),
            tools=ToolRegistry(),
            reasoner=cast(
                Reasoner,
                SimpleNamespace(
                    run_turn=AsyncMock(return_value=TurnRunResult(reply=None)),
                ),
            ),
        )
    )
    msg = InboundMessage(channel="cli", sender="hua", chat_id="1", content="hi")

    out = await agent_core.process(msg, "cli:1")

    assert "no response to give" in out.content


@pytest.mark.asyncio
async def test_agent_core_before_reasoning_can_patch_context():
    session = _DummySession("telegram:123")
    context_store = SimpleNamespace(
        prepare=AsyncMock(
            return_value=ContextBundle(
                skill_mentions=["old"],
                retrieved_memory_block="old memory",
            )
        ),
    )
    context = SimpleNamespace(
        render=MagicMock(
            return_value=SimpleNamespace(system_prompt="prompt", messages=[])
        )
    )
    tools = ToolRegistry()
    reasoner = SimpleNamespace(
        run_turn=AsyncMock(return_value=TurnRunResult(reply="ok")),
    )
    event_bus = EventBus()

    async def patch(event: ReasoningStarting) -> ReasoningStarting:
        return replace(event, skill_names=("new",), retrieved_memory_block="new memory")

    kernel = kernel_with(on=((ReasoningStarting, patch),))
    agent_core = AgentCore(
        AgentCoreDeps(
            session=cast(
                SessionServices,
                SimpleNamespace(
                    session_manager=SimpleNamespace(
                        get_or_create=MagicMock(return_value=session),
                        peek_next_message_id=MagicMock(return_value="telegram:123:0"),
                        append_messages=AsyncMock(),
                    ),
                    presence=None,
                ),
            ),
            context_store=cast(ContextStore, context_store),
            context=cast(ContextBuilder, context),
            tools=cast(ToolRegistry, tools),
            reasoner=cast(Reasoner, reasoner),
            event_bus=event_bus,
        )
    )
    agent_core.bind_kernel(lambda: kernel)
    msg = InboundMessage(channel="telegram", sender="hua", chat_id="123", content="hi")

    await agent_core.process(msg, "telegram:123")

    render_request = context.render.call_args.args[0]
    assert render_request.skill_names == ["new"]
    assert render_request.retrieved_memory_block == "new memory"
    assert reasoner.run_turn.await_args.kwargs["skill_names"] == ["new"]
    assert reasoner.run_turn.await_args.kwargs["retrieved_memory_block"] == "new memory"


def test_predict_current_user_source_ref_falls_back_to_last_session_message():
    session = _DummySession("telegram:123")
    session.messages.append({"id": "telegram:123:41"})

    value = predict_current_user_source_ref(
        session_manager=cast(SessionManager, SimpleNamespace()),
        session=cast(SessionLike, session),
    )

    assert value == "telegram:123:41"


@pytest.mark.asyncio
async def test_before_turn_abort_skips_reasoner_and_commit_and_dispatches():
    session = _DummySession("telegram:123")
    context_store = SimpleNamespace(
        prepare=AsyncMock(return_value=ContextBundle()),
    )
    context = SimpleNamespace(
        render=MagicMock(return_value=SimpleNamespace(system_prompt="p", messages=[])),
    )
    tools = ToolRegistry()
    reasoner = SimpleNamespace(run_turn=AsyncMock())
    event_bus = EventBus()
    dispatch_port = AsyncMock(return_value=True)

    async def abort_handler(event: TurnStarting) -> Veto:
        return Veto("blocked by policy")

    kernel = kernel_with(on=((TurnStarting, abort_handler),))

    agent_core = AgentCore(
        AgentCoreDeps(
            session=cast(
                SessionServices,
                SimpleNamespace(
                    session_manager=SimpleNamespace(
                        get_or_create=MagicMock(return_value=session),
                    )
                ),
            ),
            context_store=cast(ContextStore, context_store),
            context=cast(ContextBuilder, context),
            tools=cast(ToolRegistry, tools),
            reasoner=cast(Reasoner, reasoner),
            event_bus=event_bus,
            outbound_port=cast(OutboundPort, dispatch_port),
        )
    )
    agent_core.bind_kernel(lambda: kernel)
    msg = InboundMessage(channel="telegram", sender="hua", chat_id="123", content="hi")

    out = await agent_core.process(msg, "telegram:123", dispatch_outbound=True)

    assert out.content == "blocked by policy"
    # 不经过 reasoner 和持久化
    reasoner.run_turn.assert_not_called()
    # 通过 outbound_port 实际 dispatch
    dispatch_port.dispatch.assert_awaited_once()
    dispatched = dispatch_port.dispatch.await_args.args[0]
    assert dispatched.content == "blocked by policy"


@pytest.mark.asyncio
async def test_before_reasoning_abort_skips_reasoner_and_commit_and_dispatches():
    session = _DummySession("telegram:123")
    context_store = SimpleNamespace(
        prepare=AsyncMock(return_value=ContextBundle()),
    )
    context = SimpleNamespace(
        render=MagicMock(return_value=SimpleNamespace(system_prompt="p", messages=[])),
    )
    tools = ToolRegistry()
    reasoner = SimpleNamespace(run_turn=AsyncMock())
    event_bus = EventBus()
    dispatch_port = AsyncMock(return_value=True)

    async def abort_handler(event: ReasoningStarting) -> Veto:
        return Veto("rate limited")

    kernel = kernel_with(on=((ReasoningStarting, abort_handler),))

    agent_core = AgentCore(
        AgentCoreDeps(
            session=cast(
                SessionServices,
                SimpleNamespace(
                    session_manager=SimpleNamespace(
                        get_or_create=MagicMock(return_value=session),
                    )
                ),
            ),
            context_store=cast(ContextStore, context_store),
            context=cast(ContextBuilder, context),
            tools=cast(ToolRegistry, tools),
            reasoner=cast(Reasoner, reasoner),
            event_bus=event_bus,
            outbound_port=cast(OutboundPort, dispatch_port),
        )
    )
    agent_core.bind_kernel(lambda: kernel)
    msg = InboundMessage(channel="telegram", sender="hua", chat_id="123", content="hi")

    out = await agent_core.process(msg, "telegram:123", dispatch_outbound=True)

    assert out.content == "rate limited"
    reasoner.run_turn.assert_not_called()
    dispatch_port.dispatch.assert_awaited_once()
    dispatched = dispatch_port.dispatch.await_args.args[0]
    assert dispatched.content == "rate limited"


@pytest.mark.asyncio
async def test_abort_does_not_dispatch_when_dispatch_outbound_false():
    session = _DummySession("telegram:123")
    context_store = SimpleNamespace(
        prepare=AsyncMock(return_value=ContextBundle()),
    )
    context = SimpleNamespace(
        render=MagicMock(return_value=SimpleNamespace(system_prompt="p", messages=[])),
    )
    tools = ToolRegistry()
    reasoner = SimpleNamespace(run_turn=AsyncMock())
    event_bus = EventBus()
    dispatch_port = AsyncMock(return_value=True)

    async def abort_handler(event: TurnStarting) -> Veto:
        return Veto("quiet abort")

    kernel = kernel_with(on=((TurnStarting, abort_handler),))

    agent_core = AgentCore(
        AgentCoreDeps(
            session=cast(
                SessionServices,
                SimpleNamespace(
                    session_manager=SimpleNamespace(
                        get_or_create=MagicMock(return_value=session),
                    )
                ),
            ),
            context_store=cast(ContextStore, context_store),
            context=cast(ContextBuilder, context),
            tools=cast(ToolRegistry, tools),
            reasoner=cast(Reasoner, reasoner),
            event_bus=event_bus,
            outbound_port=cast(OutboundPort, dispatch_port),
        )
    )
    agent_core.bind_kernel(lambda: kernel)
    msg = InboundMessage(channel="telegram", sender="hua", chat_id="123", content="hi")

    out = await agent_core.process(msg, "telegram:123", dispatch_outbound=False)

    assert out.content == "quiet abort"
    reasoner.run_turn.assert_not_called()
    dispatch_port.dispatch.assert_not_called()


@pytest.mark.asyncio
async def test_reasoner_exception_turn_returns_control_outbound():
    session = _DummySession("telegram:123")
    context_store = SimpleNamespace(
        prepare=AsyncMock(return_value=ContextBundle()),
    )
    context = SimpleNamespace(
        render=MagicMock(return_value=SimpleNamespace(system_prompt="p", messages=[])),
    )
    tools = ToolRegistry()
    reasoner = SimpleNamespace(
        run_turn=AsyncMock(side_effect=RuntimeError("budget guard")),
    )
    dispatch_port = AsyncMock(return_value=True)

    agent_core = AgentCore(
        AgentCoreDeps(
            session=cast(
                SessionServices,
                SimpleNamespace(
                    session_manager=SimpleNamespace(
                        get_or_create=MagicMock(return_value=session),
                        peek_next_message_id=MagicMock(return_value="telegram:123:0"),
                        append_messages=AsyncMock(),
                    ),
                    presence=None,
                ),
            ),
            context_store=cast(ContextStore, context_store),
            context=cast(ContextBuilder, context),
            tools=cast(ToolRegistry, tools),
            reasoner=cast(Reasoner, reasoner),
            outbound_port=cast(OutboundPort, dispatch_port),
        )
    )
    msg = InboundMessage(channel="telegram", sender="hua", chat_id="123", content="hi")

    out = await agent_core.process(msg, "telegram:123", dispatch_outbound=True)

    assert out.content == "处理消息时出错，请稍后再试。"
    dispatch_port.dispatch.assert_awaited_once()
    dispatched = dispatch_port.dispatch.await_args.args[0]
    assert dispatched.content == "处理消息时出错，请稍后再试。"


@pytest.mark.asyncio
async def test_memory_consolidation_failure_propagates_to_transport_error():
    session = _DummySession("role:mira")
    session.messages = [{"role": "user", "content": f"u{i}"} for i in range(30)]
    context_store = SimpleNamespace(prepare=AsyncMock())
    reasoner = SimpleNamespace(run_turn=AsyncMock())

    class _FailedConsolidator:
        def request_memory_consolidation(self, session_key: str) -> None:
            raise AssertionError("failed consolidation must not be rescheduled")

        def get_memory_consolidation_failure(self, session_key: str) -> str | None:
            return "provider timeout"

    agent_core = AgentCore(
        AgentCoreDeps(
            session=cast(
                SessionServices,
                SimpleNamespace(
                    session_manager=SimpleNamespace(
                        get_or_create=MagicMock(return_value=session),
                        peek_next_message_id=MagicMock(return_value="role:mira:30"),
                        append_messages=AsyncMock(),
                    ),
                    presence=None,
                ),
            ),
            context_store=cast(ContextStore, context_store),
            context=cast(ContextBuilder, SimpleNamespace()),
            tools=ToolRegistry(),
            reasoner=cast(Reasoner, reasoner),
            history_window=20,
            memory_consolidator=_FailedConsolidator(),
        )
    )
    msg = InboundMessage(
        channel="desktop", sender="user", chat_id="role:mira", content="hi"
    )

    with pytest.raises(
        MemoryConsolidationFailedError,
        match="记忆整理失败.*provider timeout",
    ):
        await agent_core.process(msg, "role:mira", dispatch_outbound=False)

    context_store.prepare.assert_not_awaited()
    reasoner.run_turn.assert_not_awaited()


@pytest.mark.asyncio
async def test_after_turn_dispatch_exception_is_not_wrapped_by_control_outbound():
    session = _DummySession("telegram:123")
    context_store = SimpleNamespace(
        prepare=AsyncMock(return_value=ContextBundle()),
    )
    context = SimpleNamespace(
        render=MagicMock(return_value=SimpleNamespace(system_prompt="p", messages=[])),
    )
    tools = ToolRegistry()
    reasoner = SimpleNamespace(
        run_turn=AsyncMock(
            return_value=TurnRunResult(
                reply="ok",
                tools_used=[],
                tool_chain=[],
                thinking=None,
                context_retry={},
            )
        )
    )
    dispatch_port = SimpleNamespace(
        dispatch=AsyncMock(side_effect=RuntimeError("dispatch failed"))
    )

    agent_core = AgentCore(
        AgentCoreDeps(
            session=cast(
                SessionServices,
                SimpleNamespace(
                    session_manager=SimpleNamespace(
                        get_or_create=MagicMock(return_value=session),
                        peek_next_message_id=MagicMock(return_value="telegram:123:0"),
                        append_messages=AsyncMock(),
                    ),
                    presence=None,
                ),
            ),
            context_store=cast(ContextStore, context_store),
            context=cast(ContextBuilder, context),
            tools=cast(ToolRegistry, tools),
            reasoner=cast(Reasoner, reasoner),
            outbound_port=cast(OutboundPort, dispatch_port),
        )
    )
    msg = InboundMessage(channel="telegram", sender="hua", chat_id="123", content="hi")

    with pytest.raises(RuntimeError, match="dispatch failed"):
        await agent_core.process(msg, "telegram:123", dispatch_outbound=True)

    assert len(session.messages) == 2
    assert session.messages[0]["role"] == "user"
    assert session.messages[1]["role"] == "assistant"
    assert session.messages[1]["content"] == "ok"
    dispatch_port.dispatch.assert_awaited_once()
