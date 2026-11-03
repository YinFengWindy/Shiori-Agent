from __future__ import annotations

from tests.support.generation_getters import run_in_turn
from dataclasses import replace
from types import SimpleNamespace
from typing import cast
from unittest.mock import AsyncMock, MagicMock

import pytest

from agent.context import ContextBuilder
from agent.core.passive_turn import ContextStore, Reasoner
from agent.core.runtime_support import TurnRunResult
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
                        presence=MagicMock(),
                        get_or_create=MagicMock(return_value=session),
                        peek_next_message_id=MagicMock(return_value="telegram:123:0"),
                        append_messages=AsyncMock(),
                    ),
                ),
            ),
            context_store=cast(ContextStore, context_store),
            context=cast(ContextBuilder, context),
            tools=cast(ToolRegistry, tools),
            reasoner=cast(Reasoner, reasoner),
            event_bus=event_bus,
        )
    )
    run_in_turn(agent_core, method="process")
    agent_core.bind_kernel(lambda: kernel)
    msg = InboundMessage(channel="telegram", sender="hua", chat_id="123", content="hi")

    await agent_core.process(msg, "telegram:123")

    render_request = context.render.call_args.args[0]
    assert render_request.skill_names == ["new"]
    assert render_request.retrieved_memory_block == "new memory"
    assert reasoner.run_turn.await_args.kwargs["skill_names"] == ["new"]
    assert reasoner.run_turn.await_args.kwargs["retrieved_memory_block"] == "new memory"


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
                        presence=MagicMock(),
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
    run_in_turn(agent_core, method="process")
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
                        presence=MagicMock(),
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
    run_in_turn(agent_core, method="process")
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
                        presence=MagicMock(),
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
    run_in_turn(agent_core, method="process")
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
                        presence=MagicMock(),
                        get_or_create=MagicMock(return_value=session),
                        peek_next_message_id=MagicMock(return_value="telegram:123:0"),
                        append_messages=AsyncMock(),
                    ),
                ),
            ),
            context_store=cast(ContextStore, context_store),
            context=cast(ContextBuilder, context),
            tools=cast(ToolRegistry, tools),
            reasoner=cast(Reasoner, reasoner),
            outbound_port=cast(OutboundPort, dispatch_port),
        )
    )
    run_in_turn(agent_core, method="process")
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
                        presence=MagicMock(),
                        get_or_create=MagicMock(return_value=session),
                        peek_next_message_id=MagicMock(return_value="role:mira:30"),
                        append_messages=AsyncMock(),
                    ),
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
    run_in_turn(agent_core, method="process")
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
                        presence=MagicMock(),
                        get_or_create=MagicMock(return_value=session),
                        peek_next_message_id=MagicMock(return_value="telegram:123:0"),
                        append_messages=AsyncMock(),
                    ),
                ),
            ),
            context_store=cast(ContextStore, context_store),
            context=cast(ContextBuilder, context),
            tools=cast(ToolRegistry, tools),
            reasoner=cast(Reasoner, reasoner),
            outbound_port=cast(OutboundPort, dispatch_port),
        )
    )
    run_in_turn(agent_core, method="process")
    msg = InboundMessage(channel="telegram", sender="hua", chat_id="123", content="hi")

    with pytest.raises(RuntimeError, match="dispatch failed"):
        await agent_core.process(msg, "telegram:123", dispatch_outbound=True)

    assert len(session.messages) == 2
    assert session.messages[0]["role"] == "user"
    assert session.messages[1]["role"] == "assistant"
    assert session.messages[1]["content"] == "ok"
    dispatch_port.dispatch.assert_awaited_once()
