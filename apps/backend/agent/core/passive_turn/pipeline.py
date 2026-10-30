from __future__ import annotations

import hashlib
import logging
import time
from collections.abc import Callable
from dataclasses import dataclass
from typing import TYPE_CHECKING

from .context import ContextStore
from .empty_reply import EmptyReplyError
from .reasoner import Reasoner
from agent.core.turn_events import TurnEvents, core_kernel
from agent.lifecycle.phases.after_reasoning import AfterReasoningPhase
from agent.lifecycle.phases.after_turn import AfterTurnPhase
from agent.lifecycle.phases.before_reasoning import BeforeReasoningPhase
from agent.lifecycle.phases.before_turn import (
    BeforeTurnPhase,
    MemoryConsolidationFailedError,
    MemoryConsolidator,
)
from agent.lifecycle.types import (
    AfterReasoningInput,
    BeforeReasoningInput,
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
from shiori_sdk.kernel import Kernel
from core.compaction import CompactionFailedError

if TYPE_CHECKING:
    from agent.context import ContextBuilder
    from agent.core.runtime_support import TurnRunResult
    from agent.looping.ports import SessionServices
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

    def bind_kernel(self, kernel: Callable[[], Kernel]) -> None:
        """回合事件改经 ``kernel()`` 返回的内核发出（每次发出时读取）。"""
        self._passive_pipeline.bind_kernel(kernel)

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
        self._outbound_port = deps.outbound_port or _NoopOutboundPort()
        self._history_window = deps.history_window
        self._memory_consolidator = deps.memory_consolidator
        bus = deps.event_bus or EventBus()
        self._bus = bus

        # 回合事件经当前插件代的内核发出；未接插件时是只带核心校验的裸内核。
        bare_kernel = core_kernel()
        self._kernel: Callable[[], Kernel] = lambda: bare_kernel
        self._events = TurnEvents(bus, lambda: self._kernel())
        self._before_turn = BeforeTurnPhase(
            self._events,
            self._session.session_manager,
            self._context_store,
            keep_count=self._history_window,
            consolidator=self._memory_consolidator,
        )
        self._before_reasoning = BeforeReasoningPhase(
            self._events,
            self._tools,
            self._session.session_manager,
            self._context,
        )
        # after_reasoning / after_turn also publish core domain events
        # (ReplyMessageCommitted, TurnCommitted) on the same bus as ``_events``.
        self._after_reasoning = AfterReasoningPhase(
            self._bus, self._events, self._session
        )
        self._after_turn = AfterTurnPhase(
            self._bus,
            self._events,
            self._outbound_port,
            self._context,
            self._history_window,
        )

    def bind_kernel(self, kernel: Callable[[], Kernel]) -> None:
        """回合事件改经 ``kernel()`` 返回的内核发出（每次发出时读取）。"""
        self._kernel = kernel

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
            # try/except 只包前置阶段和 reasoning：在派发前兜底并返回错误提示。
            try:
                # Phase 1: BeforeTurn（会话、命令、积压守卫、上下文、TurnStarting）。
                with diagnostic_context(phase="before_turn"):
                    before_turn = await self._before_turn.run(state)
                # TurnState 存内部默认 metadata；BeforeTurnCtx 存 TurnStarting 处理器写入的，同名 key 以后者覆盖。
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

                # Phase 2: BeforeReasoning（工具上下文、ReasoningStarting、prompt warmup）。
                with diagnostic_context(phase="before_reasoning"):
                    before_reasoning = await self._before_reasoning.run(
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

                # Phase 3-4: Reasoning（BeforeStep/AfterStep 在 Reasoner 内部执行）。
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
            # Phase 5: AfterReasoning（parse、ReasoningFinished、持久化、出站消息）。
            with diagnostic_context(phase="after_reasoning"):
                after_reasoning = await self._after_reasoning.run(
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
            # Phase 6: AfterTurn（TurnCommitted fanout、TurnFinished、dispatch）。
            with diagnostic_context(phase="after_turn"):
                outbound = await self._after_turn.run(snapshot)
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
