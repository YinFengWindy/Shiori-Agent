from __future__ import annotations

import hashlib
import logging
import time
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from .context import ContextStore
from .empty_reply import EmptyReplyError
from .reasoner import Reasoner
from agent.core.turn_events import TurnEvents
from agent.lifecycle.phase import Phase
from agent.lifecycle.plugin_contributions import (
    NO_PLUGIN_CONTRIBUTIONS,
    PluginContributionSource,
)
from core.common.live_contributions import LiveContributions
from agent.lifecycle.phases.after_reasoning import (
    AfterReasoningFrame,
    default_after_reasoning_modules,
)
from agent.lifecycle.phases.after_turn import (
    AfterTurnFrame,
    default_after_turn_modules,
)
from agent.lifecycle.phases.before_reasoning import (
    BeforeReasoningFrame,
    default_before_reasoning_modules,
)
from agent.lifecycle.phases.before_turn import (
    BeforeTurnFrame,
    MemoryConsolidationFailedError,
    MemoryConsolidator,
    default_before_turn_modules,
)
from agent.lifecycle.types import (
    AfterReasoningInput,
    AfterReasoningResult,
    BeforeReasoningCtx,
    BeforeReasoningInput,
    BeforeTurnCtx,
    TurnSnapshot,
    TurnState,
)
from agent.turns.turn_pushes import TurnPushDrafts
from agent.turns.outbound import (
    DeliveryReceipt,
    OutboundDispatch,
    OutboundPort,
)
from bus.event_bus import EventBus
from shiori_sdk.messages import InboundMessage, OutboundMessage
from bus.events_lifecycle import TurnFailed
from core.common.diagnostic_log import diagnostic_context, diagnostic_line
from shiori_sdk.errors import summarize_exception_for_user
from core.compaction import CompactionFailedError

if TYPE_CHECKING:
    from agent.context import ContextBuilder
    from agent.core.runtime_support import TurnRunResult
    from agent.looping.ports import LLMConfig, LLMServices, SessionServices
    from agent.tools.registry import ToolRegistry

logger = logging.getLogger("agent.core.passive_turn")


def _turn_log_id(key: str, msg: InboundMessage) -> str:
    raw = f"{key}|{msg.timestamp.isoformat()}|{msg.content[:80]}"
    return hashlib.sha1(raw.encode("utf-8")).hexdigest()[:8]


class _NoopOutboundPort:
    async def dispatch(self, outbound: OutboundDispatch) -> DeliveryReceipt | None:
        return None


@dataclass
class AgentCoreDeps:
    """声明被动消息 pipeline 的运行时依赖。"""

    session: "SessionServices"
    context_store: "ContextStore"
    context: "ContextBuilder"
    tools: "ToolRegistry"
    reasoner: "Reasoner"
    llm: "LLMServices | None" = None
    llm_config: "LLMConfig | None" = None
    event_bus: "EventBus | None" = None
    outbound_port: "OutboundPort | None" = None
    history_window: int = 500
    memory_consolidator: MemoryConsolidator | None = None


class AgentCore:
    """
    ┌──────────────────────────────────────┐
    │ AgentCore                            │
    ├──────────────────────────────────────┤
    │ 1. 持有 PassiveTurnPipeline          │
    │ 2. 委托 pipeline 处理被动消息        │
    └──────────────────────────────────────┘
    """

    def __init__(self, deps: AgentCoreDeps) -> None:
        self._passive_pipeline = PassiveTurnPipeline(deps)

    @property
    def pipeline(self) -> "PassiveTurnPipeline":
        return self._passive_pipeline

    def bind_plugin_contributions(self, plugins: PluginContributionSource) -> None:
        """改为从 ``plugins`` 实时读取回合级阶段的插件模块。"""
        self._passive_pipeline.bind_plugin_contributions(plugins)

    async def process(
        self,
        msg: InboundMessage,
        key: str,
        *,
        dispatch_outbound: bool = True,
    ) -> OutboundMessage:
        return await self._passive_pipeline.run(
            msg,
            key,
            dispatch_outbound=dispatch_outbound,
        )


class PassiveTurnPipeline:
    """
    ┌──────────────────────────────────────┐
    │ PassiveTurnPipeline                  │
    ├──────────────────────────────────────┤
    │ 1. BeforeTurn（会话准备）             │
    │ 2. BeforeReasoning                   │
    │ 3. 执行 reasoner（含 BeforeStep/AfterStep）│
    │ 4. AfterReasoning（parse + 持久化 + 构建出站消息）│
    │ 5. AfterTurn（TurnCommitted + dispatch） │
    │ 6. 返回出站消息                      │
    └──────────────────────────────────────┘
    """

    def __init__(self, deps: AgentCoreDeps) -> None:
        self._session = deps.session
        self._context_store = deps.context_store
        self._context = deps.context
        self._tools = deps.tools
        self._reasoner = deps.reasoner
        self._llm = getattr(deps, "llm", None)
        self._llm_config = getattr(deps, "llm_config", None)
        self._outbound_port = deps.outbound_port or _NoopOutboundPort()
        self._history_window = deps.history_window
        self._memory_consolidator = deps.memory_consolidator
        bus = deps.event_bus or EventBus()
        self._bus = bus

        # 插件模块每回合从当前插件来源读取，贡献变化时才重建阶段（#855）。
        self._plugins = NO_PLUGIN_CONTRIBUTIONS
        # 回合事件经当前来源的内核发出（未接插件时是只带核心校验的裸内核）。
        self._events = TurnEvents(bus, lambda: self._plugins.kernel)
        self._before_turn = LiveContributions(
            lambda: self._plugins.before_turn_modules,
            self._build_before_turn_phase,
        )
        self._before_reasoning = LiveContributions(
            lambda: self._plugins.before_reasoning_modules,
            self._build_before_reasoning_phase,
        )
        self._after_reasoning = LiveContributions(
            lambda: self._plugins.after_reasoning_modules,
            self._build_after_reasoning_phase,
        )
        self._after_turn = LiveContributions(
            lambda: self._plugins.after_turn_modules,
            self._build_after_turn_phase,
        )

    def bind_plugin_contributions(self, plugins: PluginContributionSource) -> None:
        """改为从 ``plugins`` 实时读取回合级阶段的插件模块。"""
        self._plugins = plugins
        # 绑定时立即按当前贡献构造一次，模块 slot 冲突等装配错误在启动时暴露。
        self._before_turn.current()
        self._before_reasoning.current()
        self._after_reasoning.current()
        self._after_turn.current()

    def _build_before_turn_phase(
        self,
        plugin_modules: list[Any],
    ) -> Phase[TurnState, BeforeTurnCtx, BeforeTurnFrame]:
        return Phase(
            default_before_turn_modules(
                self._bus,
                self._events,
                self._session.session_manager,
                self._context_store,
                keep_count=self._history_window,
                consolidator=self._memory_consolidator,
                plugin_modules=plugin_modules,
            ),
            frame_factory=BeforeTurnFrame,
        )

    def _build_before_reasoning_phase(
        self,
        plugin_modules: list[Any],
    ) -> Phase[BeforeReasoningInput, BeforeReasoningCtx, BeforeReasoningFrame]:
        return Phase(
            default_before_reasoning_modules(
                self._bus,
                self._events,
                self._tools,
                self._session.session_manager,
                self._context,
                plugin_modules=plugin_modules,
            ),
            frame_factory=BeforeReasoningFrame,
        )

    def _build_after_reasoning_phase(
        self,
        plugin_modules: list[Any],
    ) -> Phase[AfterReasoningInput, AfterReasoningResult, AfterReasoningFrame]:
        return Phase(
            default_after_reasoning_modules(
                self._bus,
                self._events,
                self._session,
                self._llm,
                self._llm_config,
                plugin_modules=plugin_modules,
            ),
            frame_factory=AfterReasoningFrame,
        )

    def _build_after_turn_phase(
        self,
        plugin_modules: list[Any],
    ) -> Phase[TurnSnapshot, OutboundMessage, AfterTurnFrame]:
        return Phase(
            default_after_turn_modules(
                self._bus,
                self._events,
                self._outbound_port,
                self._context,
                self._history_window,
                plugin_modules=plugin_modules,
                relationship_runtime=getattr(
                    self._session, "relationship_runtime", None
                ),
            ),
            frame_factory=AfterTurnFrame,
        )

    # 核心方法：处理一条普通被动消息，并提交最终出站结果。
    async def run(
        self,
        msg: InboundMessage,
        key: str,
        *,
        dispatch_outbound: bool = True,
    ) -> OutboundMessage:
        pushes = TurnPushDrafts(key, started_at=msg.timestamp)
        state = TurnState(
            msg=msg,
            session_key=key,
            dispatch_outbound=dispatch_outbound,
            turn_pushes=pushes,
        )
        # A turn that did not commit still records what it already delivered
        # (no-op after a commit); a failure to record never replaces the turn's
        # own error.
        try:
            outbound = await self._run(state, msg, key)
        except BaseException as exc:
            await pushes.abandoned(turn_error=exc)
            raise
        await pushes.abandoned()
        return outbound

    async def _run(
        self, state: TurnState, msg: InboundMessage, key: str
    ) -> OutboundMessage:
        started = time.perf_counter()
        turn_id = _turn_log_id(key, msg)
        with diagnostic_context(session=key, flow="passive", turn=turn_id):
            logger.info(
                diagnostic_line(
                    "PassiveTurnPipeline.run",
                    event="start",
                    flow="passive",
                    phase="before_turn",
                    session=key,
                    turn=turn_id,
                    action="run",
                )
            )
            # try/except 只包前置模块链和 reasoning：在派发前兜底并返回错误提示。
            try:
                # Phase 1: BeforeTurn 模块链（会话、上下文、BeforeTurn 事件）。
                with diagnostic_context(phase="before_turn"):
                    before_turn = await self._before_turn.current().run(state)
                # TurnState 存内部默认 metadata；BeforeTurnCtx 存插件导出，同名 key 以后者覆盖。
                state.extra_metadata.update(before_turn.extra_metadata)
                if before_turn.abort:
                    logger.info(
                        diagnostic_line(
                            "PassiveTurnPipeline.run",
                            event="gate_exit",
                            flow="passive",
                            phase="before_turn",
                            session=key,
                            turn=turn_id,
                            action="abort",
                            reason="before_turn_abort",
                            duration_ms=int((time.perf_counter() - started) * 1000),
                        )
                    )
                    return await self._control_outbound(
                        state,
                        OutboundMessage(
                            channel=msg.channel,
                            chat_id=msg.chat_id,
                            content=before_turn.abort_reply,
                        ),
                    )
                logger.info(
                    diagnostic_line(
                        "PassiveTurnPipeline.run",
                        event="end",
                        flow="passive",
                        phase="before_turn",
                        session=key,
                        turn=turn_id,
                        action="continue",
                        duration_ms=int((time.perf_counter() - started) * 1000),
                    )
                )

                # Phase 2: BeforeReasoning 模块链（工具上下文、BeforeReasoning 事件、prompt warmup）。
                with diagnostic_context(phase="before_reasoning"):
                    before_reasoning = await self._before_reasoning.current().run(
                        BeforeReasoningInput(state=state, before_turn=before_turn)
                    )
                if before_reasoning.abort:
                    logger.info(
                        diagnostic_line(
                            "PassiveTurnPipeline.run",
                            event="gate_exit",
                            flow="passive",
                            phase="before_reasoning",
                            session=key,
                            turn=turn_id,
                            action="abort",
                            reason="before_reasoning_abort",
                            duration_ms=int((time.perf_counter() - started) * 1000),
                        )
                    )
                    return await self._control_outbound(
                        state,
                        OutboundMessage(
                            channel=msg.channel,
                            chat_id=msg.chat_id,
                            content=before_reasoning.abort_reply,
                        ),
                    )
                logger.info(
                    diagnostic_line(
                        "PassiveTurnPipeline.run",
                        event="end",
                        flow="passive",
                        phase="before_reasoning",
                        session=key,
                        turn=turn_id,
                        action="continue",
                        counts=f"skills:{len(before_reasoning.skill_names)},hints:{len(before_reasoning.extra_hints)}",
                        duration_ms=int((time.perf_counter() - started) * 1000),
                    )
                )

                # Phase 3-4: Reasoning（BeforeStep/AfterStep 模块链在 Reasoner 内部执行）。
                session = state.session
                if session is None:
                    raise RuntimeError("Passive turn requires TurnState.session")
                assert state.turn_pushes is not None
                with (
                    diagnostic_context(phase="reasoner"),
                    state.turn_pushes.collect(),
                ):
                    turn_result = await self._reasoner.run_turn(
                        msg=msg,
                        skill_names=list(before_reasoning.skill_names) or None,
                        session=session,
                        base_history=None,
                        retrieved_memory_block=before_reasoning.retrieved_memory_block,
                        extra_hints=list(before_reasoning.extra_hints) or None,
                        context_view=state.context_view,
                    )
                logger.info(
                    diagnostic_line(
                        "PassiveTurnPipeline.run",
                        event="end",
                        flow="passive",
                        phase="reasoner",
                        session=key,
                        turn=turn_id,
                        action="continue",
                        duration_ms=int((time.perf_counter() - started) * 1000),
                    )
                )
            except (MemoryConsolidationFailedError, CompactionFailedError):
                raise
            except Exception as exc:
                if isinstance(exc, EmptyReplyError):
                    # This bounded payload is the diagnosis. A chained provider
                    # traceback can exceed the collector limit and cut it off.
                    logger.error("EmptyReplyError: %s", exc)
                else:
                    logger.exception(
                        diagnostic_line(
                            "PassiveTurnPipeline.run",
                            event="phase_error",
                            flow="passive",
                            phase="reasoner",
                            session=key,
                            turn=turn_id,
                            action="fail",
                            reason="provider_error",
                            duration_ms=int((time.perf_counter() - started) * 1000),
                            error_type=type(exc).__name__,
                            note=str(exc)[:160],
                        )
                    )
                # The reply below stays generic; surfaces that can show more
                # (the desktop's 「详情」) pick up a scrubbed one-line summary.
                await self._bus.observe(
                    TurnFailed(
                        session_key=key,
                        error_summary=summarize_exception_for_user(exc),
                    )
                )
                return await self._control_outbound(
                    state,
                    OutboundMessage(
                        channel=msg.channel,
                        chat_id=msg.chat_id,
                        content="处理消息时出错，请稍后再试。",
                    ),
                )

            return await self._commit_and_dispatch(state, turn_result, started=started)

    async def _commit_and_dispatch(
        self,
        state: TurnState,
        turn_result: "TurnRunResult",
        *,
        started: float | None = None,
    ) -> OutboundMessage:
        """Commit history, then fan out and dispatch the resulting reply."""
        started = time.perf_counter() if started is None else started
        key = state.session_key
        turn_id = _turn_log_id(key, state.msg)
        try:
            # Phase 5: AfterReasoning 模块链（parse、AfterReasoning 事件、持久化、出站消息）。
            with diagnostic_context(phase="after_reasoning"):
                after_reasoning = await self._after_reasoning.current().run(
                    AfterReasoningInput(state=state, turn_result=turn_result)
                )
        except Exception as exc:
            logger.exception(
                diagnostic_line(
                    "PassiveTurnPipeline.run",
                    event="phase_error",
                    flow="passive",
                    phase="after_reasoning",
                    session=key,
                    turn=turn_id,
                    action="fail",
                    reason="invalid_output",
                    duration_ms=int((time.perf_counter() - started) * 1000),
                    error_type=type(exc).__name__,
                    note=str(exc)[:160],
                )
            )
            raise
        logger.info(
            diagnostic_line(
                "PassiveTurnPipeline.run",
                event="end",
                flow="passive",
                phase="after_reasoning",
                session=key,
                turn=turn_id,
                action="continue",
                duration_ms=int((time.perf_counter() - started) * 1000),
            )
        )

        snapshot = TurnSnapshot(
            state=state, outbound=after_reasoning.outbound, ctx=after_reasoning.ctx
        )
        try:
            # Phase 6: AfterTurn 模块链（TurnCommitted fanout、AfterTurn fanout、dispatch）。
            with diagnostic_context(phase="after_turn"):
                outbound = await self._after_turn.current().run(snapshot)
        except Exception as exc:
            logger.exception(
                diagnostic_line(
                    "PassiveTurnPipeline.run",
                    event="phase_error",
                    flow="passive",
                    phase="after_turn",
                    session=key,
                    turn=turn_id,
                    action="fail",
                    reason="write_error",
                    duration_ms=int((time.perf_counter() - started) * 1000),
                    error_type=type(exc).__name__,
                    note=str(exc)[:160],
                )
            )
            raise
        logger.info(
            diagnostic_line(
                "PassiveTurnPipeline.run",
                event="end",
                flow="passive",
                phase="after_turn",
                session=key,
                turn=turn_id,
                action="done",
                duration_ms=int((time.perf_counter() - started) * 1000),
            )
        )
        return outbound

    # 供外部调用方（如 spawn completion）复用 AfterReasoning + dispatch 流程。
    async def post_reasoning(
        self,
        msg: InboundMessage,
        session_key: str,
        turn_result: "TurnRunResult",
        *,
        dispatch_outbound: bool = True,
    ) -> OutboundMessage:
        state = TurnState(
            msg=msg,
            session_key=session_key,
            dispatch_outbound=dispatch_outbound,
            session=self._session.session_manager.get_or_create(session_key),
        )
        return await self._commit_and_dispatch(state, turn_result)

    # abort / 错误路径的统一 dispatch helper，只有 dispatch_outbound=True 时才发送。
    async def _control_outbound(
        self,
        state: TurnState,
        outbound: OutboundMessage,
    ) -> OutboundMessage:
        if state.dispatch_outbound:
            metadata = dict(state.msg.metadata or {})
            metadata.update(outbound.metadata or {})
            # No special-casing needed for the error/abort fallback paths that call
            # this helper: their OutboundMessage never carries a committed_message_id
            # (nothing was persisted), so it naturally stays unset here too, and
            # mark_delivery skips writing a delivery mark for them downstream.
            _ = await self._outbound_port.dispatch(
                OutboundDispatch(
                    channel=outbound.channel,
                    chat_id=outbound.chat_id,
                    content=outbound.content,
                    thinking=outbound.thinking,
                    metadata=metadata,
                    media=outbound.media,
                    committed_message_id=outbound.committed_message_id,
                )
            )
        return outbound
