from __future__ import annotations

import asyncio
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
from bus.events import InboundMessage
from agent.lifecycle.types import BeforeReasoningCtx, BeforeTurnCtx
from agent.lifecycle.phases.before_turn import MemoryConsolidationFailedError
from core.roles.reply_state import InvalidRoleReply
from session.manager import SessionManager


class _DummySession:
    def __init__(self, key: str) -> None:
        self.key = key
        self.messages: list[dict] = []
        self.metadata: dict[str, object] = {}
        self.last_consolidated = 0
        self.updated_at = datetime.now()

    def get_history(
        self,
        max_messages: int = 500,
        *,
        start_index: int | None = None,
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
    tools = SimpleNamespace(
        set_context=MagicMock(side_effect=lambda **kwargs: order.append("tool_context"))
    )
    reasoner = SimpleNamespace(
        run_turn=AsyncMock(
            side_effect=lambda *args, **kwargs: order.append("run")
            or TurnRunResult(
                reply="final <meme:shy>\n§cited:[mem_1]§",
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

    assert out.content == "final <meme:shy>\n§cited:[mem_1]§"
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
        role_id="",
        current_user_message="你好",
        role_config_version="",
        thread_id="",
        delivery_key="",
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
    assert session.messages[1]["content"] == "final <meme:shy>\n§cited:[mem_1]§"


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
            tools=cast(
                ToolRegistry,
                SimpleNamespace(set_context=MagicMock()),
            ),
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
    tools = SimpleNamespace(set_context=MagicMock())
    reasoner = SimpleNamespace(
        run_turn=AsyncMock(return_value=TurnRunResult(reply="ok")),
    )
    event_bus = EventBus()

    event_bus.on(
        BeforeReasoningCtx,
        lambda ctx: BeforeReasoningCtx(
            session_key=ctx.session_key,
            channel=ctx.channel,
            chat_id=ctx.chat_id,
            content=ctx.content,
            timestamp=ctx.timestamp,
            skill_names=["new"],
            retrieved_memory_block="new memory",
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
            event_bus=event_bus,
        )
    )
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
    tools = SimpleNamespace(set_context=MagicMock())
    reasoner = SimpleNamespace(run_turn=AsyncMock())
    event_bus = EventBus()
    dispatch_port = AsyncMock(return_value=True)

    async def abort_handler(ctx):
        ctx.abort = True
        ctx.abort_reply = "blocked by policy"
        return ctx

    event_bus.on(BeforeTurnCtx, abort_handler)

    agent_core = AgentCore(
        AgentCoreDeps(
            session=cast(
                SessionServices,
                SimpleNamespace(
                    session_manager=SimpleNamespace(
                        get_or_create=MagicMock(return_value=session),
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
            outbound_port=cast(OutboundPort, dispatch_port),
        )
    )
    msg = InboundMessage(channel="telegram", sender="hua", chat_id="123", content="hi")

    out = await agent_core.process(msg, "telegram:123", dispatch_outbound=True)

    assert out.content == "blocked by policy"
    # 不经过 reasoner，也不提交任何助手回复
    reasoner.run_turn.assert_not_called()
    # 通过 outbound_port 实际 dispatch
    dispatch_port.dispatch.assert_awaited_once()
    dispatched = dispatch_port.dispatch.await_args.args[0]
    assert dispatched.content == "blocked by policy"
    # Issue #306：早落库发生在 before_turn 链最前面（acquire_session 之后），
    # 早于这个 abort 判断本身，所以即便这一轮被 before_turn 拦截，用户这句话
    # 依然进了历史——这是"一处覆盖所有失败路径"的直接后果，不是意外。
    assert len(session.messages) == 1
    assert session.messages[0]["role"] == "user"
    assert session.messages[0]["content"] == "hi"


@pytest.mark.asyncio
async def test_before_reasoning_abort_skips_reasoner_and_commit_and_dispatches():
    session = _DummySession("telegram:123")
    context_store = SimpleNamespace(
        prepare=AsyncMock(return_value=ContextBundle()),
    )
    context = SimpleNamespace(
        render=MagicMock(return_value=SimpleNamespace(system_prompt="p", messages=[])),
    )
    tools = SimpleNamespace(set_context=MagicMock())
    reasoner = SimpleNamespace(run_turn=AsyncMock())
    event_bus = EventBus()
    dispatch_port = AsyncMock(return_value=True)

    async def abort_handler(ctx):
        ctx.abort = True
        ctx.abort_reply = "rate limited"
        return ctx

    event_bus.on(BeforeReasoningCtx, abort_handler)

    agent_core = AgentCore(
        AgentCoreDeps(
            session=cast(
                SessionServices,
                SimpleNamespace(
                    session_manager=SimpleNamespace(
                        get_or_create=MagicMock(return_value=session),
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
            outbound_port=cast(OutboundPort, dispatch_port),
        )
    )
    msg = InboundMessage(channel="telegram", sender="hua", chat_id="123", content="hi")

    out = await agent_core.process(msg, "telegram:123", dispatch_outbound=True)

    assert out.content == "rate limited"
    reasoner.run_turn.assert_not_called()
    dispatch_port.dispatch.assert_awaited_once()
    dispatched = dispatch_port.dispatch.await_args.args[0]
    assert dispatched.content == "rate limited"
    # Issue #306：before_turn 早就跑完了（含早落库），before_reasoning 的 abort
    # 不影响用户消息已经落库这个事实。
    assert len(session.messages) == 1
    assert session.messages[0]["role"] == "user"
    assert session.messages[0]["content"] == "hi"


@pytest.mark.asyncio
async def test_abort_does_not_dispatch_when_dispatch_outbound_false():
    session = _DummySession("telegram:123")
    context_store = SimpleNamespace(
        prepare=AsyncMock(return_value=ContextBundle()),
    )
    context = SimpleNamespace(
        render=MagicMock(return_value=SimpleNamespace(system_prompt="p", messages=[])),
    )
    tools = SimpleNamespace(set_context=MagicMock())
    reasoner = SimpleNamespace(run_turn=AsyncMock())
    event_bus = EventBus()
    dispatch_port = AsyncMock(return_value=True)

    async def abort_handler(ctx):
        ctx.abort = True
        ctx.abort_reply = "quiet abort"
        return ctx

    event_bus.on(BeforeTurnCtx, abort_handler)

    agent_core = AgentCore(
        AgentCoreDeps(
            session=cast(
                SessionServices,
                SimpleNamespace(
                    session_manager=SimpleNamespace(
                        get_or_create=MagicMock(return_value=session),
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
            outbound_port=cast(OutboundPort, dispatch_port),
        )
    )
    msg = InboundMessage(channel="telegram", sender="hua", chat_id="123", content="hi")

    out = await agent_core.process(msg, "telegram:123", dispatch_outbound=False)

    assert out.content == "quiet abort"
    reasoner.run_turn.assert_not_called()
    dispatch_port.dispatch.assert_not_called()
    # Issue #306：dispatch_outbound=False 只影响是否往外发，不影响早落库——
    # 用户消息依然进了历史。
    assert len(session.messages) == 1
    assert session.messages[0]["role"] == "user"


@pytest.mark.asyncio
async def test_reasoner_exception_turn_returns_control_outbound():
    session = _DummySession("telegram:123")
    context_store = SimpleNamespace(
        prepare=AsyncMock(return_value=ContextBundle()),
    )
    context = SimpleNamespace(
        render=MagicMock(return_value=SimpleNamespace(system_prompt="p", messages=[])),
    )
    tools = SimpleNamespace(set_context=MagicMock())
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
    # Issue #306: provider 报错（reasoner.run_turn 抛错）不应把用户这句话从历史里丢掉，
    # 即使这一轮角色没能回复。用户消息在进入 reasoning 前已经落库。
    assert len(session.messages) == 1
    assert session.messages[0]["role"] == "user"
    assert session.messages[0]["content"] == "hi"


@pytest.mark.asyncio
async def test_reasoner_memory_budget_failure_still_persists_user_message():
    """Issue #306: reasoner.run_turn 内部因超出输入预算抛出
    MemoryConsolidationFailedError 时，用户消息也不应从历史里消失。"""
    session = _DummySession("telegram:123")
    context_store = SimpleNamespace(prepare=AsyncMock(return_value=ContextBundle()))
    context = SimpleNamespace(
        render=MagicMock(return_value=SimpleNamespace(system_prompt="p", messages=[])),
    )
    tools = SimpleNamespace(set_context=MagicMock())
    reasoner = SimpleNamespace(
        run_turn=AsyncMock(
            side_effect=MemoryConsolidationFailedError(
                "记忆整理后输入仍超过预算，已停止发送超限上下文。"
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
    msg = InboundMessage(channel="telegram", sender="hua", chat_id="123", content="hi")

    with pytest.raises(MemoryConsolidationFailedError):
        await agent_core.process(msg, "telegram:123", dispatch_outbound=False)

    assert len(session.messages) == 1
    assert session.messages[0]["role"] == "user"
    assert session.messages[0]["content"] == "hi"


@pytest.mark.asyncio
async def test_reasoner_cancelled_turn_still_persists_user_message():
    """Issue #306: 回合被取消（reasoner.run_turn 抛 CancelledError）时，
    用户消息也不应从历史里消失。"""
    session = _DummySession("telegram:123")
    context_store = SimpleNamespace(prepare=AsyncMock(return_value=ContextBundle()))
    context = SimpleNamespace(
        render=MagicMock(return_value=SimpleNamespace(system_prompt="p", messages=[])),
    )
    tools = SimpleNamespace(set_context=MagicMock())
    reasoner = SimpleNamespace(run_turn=AsyncMock(side_effect=asyncio.CancelledError()))

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
    msg = InboundMessage(channel="telegram", sender="hua", chat_id="123", content="hi")

    with pytest.raises(asyncio.CancelledError):
        await agent_core.process(msg, "telegram:123", dispatch_outbound=False)

    assert len(session.messages) == 1
    assert session.messages[0]["role"] == "user"
    assert session.messages[0]["content"] == "hi"


@pytest.mark.asyncio
async def test_invalid_role_reply_still_persists_user_message():
    """Issue #306 复现原始事故：formal_role_reply 缺少已生成的心情/想法状态时
    AfterReasoning 的 build_ctx 会抛 InvalidRoleReply（"格式非法"），此前会连带
    丢掉用户这句话——用户早落库后不应再受影响。"""
    session = _DummySession("role:mira")
    context_store = SimpleNamespace(prepare=AsyncMock(return_value=ContextBundle()))
    context = SimpleNamespace(
        render=MagicMock(return_value=SimpleNamespace(system_prompt="p", messages=[])),
    )
    tools = SimpleNamespace(set_context=MagicMock())
    reasoner = SimpleNamespace(
        run_turn=AsyncMock(
            return_value=TurnRunResult(
                reply="reply text",
                context_retry={"formal_role_reply": True},
                role_reply=None,
            )
        )
    )

    agent_core = AgentCore(
        AgentCoreDeps(
            session=cast(
                SessionServices,
                SimpleNamespace(
                    session_manager=SimpleNamespace(
                        get_or_create=MagicMock(return_value=session),
                        peek_next_message_id=MagicMock(return_value="role:mira:0"),
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
        channel="qqbot",
        sender="yinfeng",
        chat_id="mira",
        content="在开会捏，昨天12点睡的",
    )

    with pytest.raises(InvalidRoleReply):
        await agent_core.process(msg, "role:mira", dispatch_outbound=False)

    assert len(session.messages) == 1
    assert session.messages[0]["role"] == "user"
    assert session.messages[0]["content"] == "在开会捏，昨天12点睡的"


@pytest.mark.asyncio
async def test_omit_user_turn_skips_early_persist_on_provider_error():
    """主动回复/调度任务等 omit_user_turn 回合不受早落库影响：provider 报错时
    仍然不写入任何用户消息。"""
    session = _DummySession("scheduler:job-1")
    context_store = SimpleNamespace(prepare=AsyncMock(return_value=ContextBundle()))
    context = SimpleNamespace(
        render=MagicMock(return_value=SimpleNamespace(system_prompt="p", messages=[])),
    )
    tools = SimpleNamespace(set_context=MagicMock())
    reasoner = SimpleNamespace(
        run_turn=AsyncMock(side_effect=RuntimeError("budget guard")),
    )

    agent_core = AgentCore(
        AgentCoreDeps(
            session=cast(
                SessionServices,
                SimpleNamespace(
                    session_manager=SimpleNamespace(
                        get_or_create=MagicMock(return_value=session),
                        peek_next_message_id=MagicMock(
                            return_value="scheduler:job-1:0"
                        ),
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
        channel="cli",
        sender="scheduler",
        chat_id="job-1",
        content="内部提示词",
        metadata={"omit_user_turn": True},
    )

    out = await agent_core.process(msg, "scheduler:job-1", dispatch_outbound=False)

    assert out.content == "处理消息时出错，请稍后再试。"
    assert session.messages == []


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
            tools=cast(ToolRegistry, SimpleNamespace()),
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
    # Issue #306 gap #1：会话存在粘滞的记忆整理失败记录时，_MemoryContextGuardModule
    # 会在 before_turn 阶段（早落库步骤之前）就抛出 MemoryConsolidationFailedError。
    # 如果用户连发多条消息，在修复前这些消息会全部从历史里消失；这里验证用户这句
    # 话仍然落库到了 session.messages 末尾。
    assert len(session.messages) == 31
    assert session.messages[-1]["role"] == "user"
    assert session.messages[-1]["content"] == "hi"


@pytest.mark.asyncio
async def test_memory_context_guard_trigger_turn_unchanged_by_early_persist(
    tmp_path,
):
    """Issue #306 gap #3（黑盒版）：早落库把当轮用户消息提前写进了
    session.messages，_MemoryContextGuardModule 必须显式排除它，否则会把
    同一条消息数两遍、让触发提前一轮。这里只断言外部可观察行为（是否触发、
    在哪一轮触发），不 monkeypatch 私有方法：keep_count=20 时
    threshold=30；历史 29 条时发一条不应触发（threshold 只数到 29，还差
    1），历史变成 31 条后再发一条才应该触发（29 旧 + 上一轮落库的 user +
    assistant = 31 >= 30）——这正是早落库之前同一个公式会给出的判断，
    证明触发轮次没有变。同时覆盖 #306 gap #2 里 reviewer 指出的另一条缺口：
    consolidator=None 时守卫不抛异常、只产出 abort，这里验证即便这一轮被
    守卫拦截，用户消息也已经落库（早落库发生在守卫判断之前）。
    """
    from agent.core.passive_turn.pipeline import PassiveTurnPipeline

    session_manager = SessionManager(tmp_path)
    session = session_manager.get_or_create("role:mira")
    for i in range(29):
        session.add_message("user" if i % 2 == 0 else "assistant", f"m{i}")
    await session_manager.append_messages(session, session.messages[:])

    reasoner = SimpleNamespace(
        run_turn=AsyncMock(return_value=TurnRunResult(reply="ok", context_retry={}))
    )
    pipeline = PassiveTurnPipeline(
        AgentCoreDeps(
            session=cast(
                SessionServices,
                SimpleNamespace(session_manager=session_manager, presence=None),
            ),
            context_store=cast(
                ContextStore,
                SimpleNamespace(prepare=AsyncMock(return_value=ContextBundle())),
            ),
            context=cast(
                ContextBuilder,
                SimpleNamespace(
                    render=MagicMock(
                        return_value=SimpleNamespace(system_prompt="p", messages=[])
                    )
                ),
            ),
            tools=cast(ToolRegistry, SimpleNamespace(set_context=MagicMock())),
            reasoner=cast(Reasoner, reasoner),
            event_bus=EventBus(),
            history_window=20,
            memory_consolidator=None,
        )
    )

    # 历史 29 条：不应触发，reasoner 正常跑，助手回复正常提交。
    out1 = await pipeline.run(
        InboundMessage(channel="qqbot", sender="u", chat_id="mira", content="turn-1"),
        "role:mira",
        dispatch_outbound=False,
    )
    assert out1.content == "ok"
    reasoner.run_turn.assert_awaited_once()
    session = session_manager.get_or_create("role:mira")
    assert len(session.messages) == 31  # 29 旧历史 + 本轮 user + assistant

    # 历史 31 条：触发（consolidator=None 时守卫走 abort 分支，不抛异常）。
    out2 = await pipeline.run(
        InboundMessage(channel="qqbot", sender="u", chat_id="mira", content="turn-2"),
        "role:mira",
        dispatch_outbound=False,
    )
    assert "记忆归档现在处于异常积压状态" in out2.content
    reasoner.run_turn.assert_awaited_once()  # 第二轮没有再调用 reasoner
    session = session_manager.get_or_create("role:mira")
    # 触发轮的用户消息依然落库了（早落库发生在守卫判断之前），只是没有助手回复。
    assert len(session.messages) == 32
    assert session.messages[-1]["role"] == "user"
    assert session.messages[-1]["content"] == "turn-2"


@pytest.mark.asyncio
async def test_cancelled_during_before_reasoning_window_still_persists_user_message():
    """Issue #306 gap #2：before_reasoning 窗口（记忆检索、prompt warmup 等，
    秒级）内发生的取消，`asyncio.CancelledError` 是 BaseException，
    `except Exception` 接不住。早落库现在发生在 before_turn 链最前面，早于
    整个 before_reasoning 阶段，这里模拟 prompt warmup 步骤（context.render）
    被取消，验证用户消息依然落库、异常照常传播。"""
    session = _DummySession("telegram:123")
    context_store = SimpleNamespace(prepare=AsyncMock(return_value=ContextBundle()))
    context = SimpleNamespace(render=MagicMock(side_effect=asyncio.CancelledError()))
    tools = SimpleNamespace(set_context=MagicMock())
    reasoner = SimpleNamespace(run_turn=AsyncMock())

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
    msg = InboundMessage(channel="telegram", sender="hua", chat_id="123", content="hi")

    with pytest.raises(asyncio.CancelledError):
        await agent_core.process(msg, "telegram:123", dispatch_outbound=False)

    reasoner.run_turn.assert_not_called()
    assert len(session.messages) == 1
    assert session.messages[0]["role"] == "user"
    assert session.messages[0]["content"] == "hi"


@pytest.mark.asyncio
async def test_after_turn_dispatch_exception_is_not_wrapped_by_control_outbound():
    session = _DummySession("telegram:123")
    context_store = SimpleNamespace(
        prepare=AsyncMock(return_value=ContextBundle()),
    )
    context = SimpleNamespace(
        render=MagicMock(return_value=SimpleNamespace(system_prompt="p", messages=[])),
    )
    tools = SimpleNamespace(set_context=MagicMock())
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


@pytest.mark.asyncio
async def test_failed_turn_user_message_keeps_seq_order_with_real_session_manager(
    tmp_path,
):
    """Issue #306 端到端顺序验证：用一个真实 SessionManager（真实落盘 + seq
    分配）跑三轮，中间一轮 reasoning 报错。失败回合的用户消息应该落库、且不
    产生半条助手消息；随后一轮的 user/assistant 消息 seq 仍然严格递增，不会
    因为落库时机提前而排到上一轮助手消息之前。"""
    from agent.core.passive_turn.pipeline import PassiveTurnPipeline

    session_manager = SessionManager(tmp_path)
    reasoner = SimpleNamespace(
        run_turn=AsyncMock(
            side_effect=[
                TurnRunResult(reply="第一轮回复", context_retry={}),
                RuntimeError("provider down"),
                TurnRunResult(reply="第三轮回复", context_retry={}),
            ]
        )
    )
    pipeline = PassiveTurnPipeline(
        AgentCoreDeps(
            session=cast(
                SessionServices,
                SimpleNamespace(session_manager=session_manager, presence=None),
            ),
            context_store=cast(
                ContextStore,
                SimpleNamespace(prepare=AsyncMock(return_value=ContextBundle())),
            ),
            context=cast(
                ContextBuilder,
                SimpleNamespace(
                    render=MagicMock(
                        return_value=SimpleNamespace(system_prompt="p", messages=[])
                    )
                ),
            ),
            tools=cast(ToolRegistry, SimpleNamespace(set_context=MagicMock())),
            reasoner=cast(Reasoner, reasoner),
            event_bus=EventBus(),
        )
    )

    for content in ("第一句", "第二句会失败", "第三句"):
        await pipeline.run(
            InboundMessage(
                channel="qqbot", sender="u", chat_id="mira", content=content
            ),
            "qqbot:mira",
            dispatch_outbound=False,
        )

    session = session_manager.get_or_create("qqbot:mira")
    roles_and_content = [(m["role"], m["content"]) for m in session.messages]
    assert roles_and_content == [
        ("user", "第一句"),
        ("assistant", "第一轮回复"),
        ("user", "第二句会失败"),
        ("user", "第三句"),
        ("assistant", "第三轮回复"),
    ]
    seqs = [m["seq"] for m in session.messages]
    assert seqs == sorted(seqs)
    assert len(set(seqs)) == len(seqs)


@pytest.mark.asyncio
async def test_successful_turn_backfills_llm_user_content_to_disk(tmp_path):
    """Issue #306 gap #1（真回归修复验证）：早落库时用户消息已经拿到 id；
    `_persist_messages` 只插入没有 id 的消息，`_PersistUserMessageModule`
    补写 llm_user_content 后如果只改内存 dict，这个字段永远到不了数据库
    ——PR 引入这个 bug 之前，成功回合的用户消息本来就是带着
    llm_user_content 一次性插入的。这里用一个全新打开、指向同一个
    sessions.db 的 SessionManager 读取（绕开原实例的内存缓存），证明
    reasoning 成功后 llm_user_content 真的写回了磁盘，不只是停留在内存里。
    """
    from agent.core.passive_turn.pipeline import PassiveTurnPipeline

    session_manager = SessionManager(tmp_path)
    reasoner = SimpleNamespace(
        run_turn=AsyncMock(
            return_value=TurnRunResult(
                reply="ok",
                context_retry={
                    "llm_user_content": "渲染后的用户内容",
                    "llm_context_frame": "渲染后的上下文 frame",
                },
            )
        )
    )
    pipeline = PassiveTurnPipeline(
        AgentCoreDeps(
            session=cast(
                SessionServices,
                SimpleNamespace(session_manager=session_manager, presence=None),
            ),
            context_store=cast(
                ContextStore,
                SimpleNamespace(prepare=AsyncMock(return_value=ContextBundle())),
            ),
            context=cast(
                ContextBuilder,
                SimpleNamespace(
                    render=MagicMock(
                        return_value=SimpleNamespace(system_prompt="p", messages=[])
                    )
                ),
            ),
            tools=cast(ToolRegistry, SimpleNamespace(set_context=MagicMock())),
            reasoner=cast(Reasoner, reasoner),
            event_bus=EventBus(),
        )
    )

    await pipeline.run(
        InboundMessage(channel="qqbot", sender="u", chat_id="mira", content="hi"),
        "role:mira",
        dispatch_outbound=False,
    )

    # 绕开原 session_manager 的内存缓存，直接从磁盘重新加载。
    fresh_manager = SessionManager(tmp_path)
    fresh_session = fresh_manager.get_or_create("role:mira")
    user_message = next(m for m in fresh_session.messages if m["role"] == "user")
    assert user_message["llm_user_content"] == "渲染后的用户内容"
    assert user_message["llm_context_frame"] == "渲染后的上下文 frame"
