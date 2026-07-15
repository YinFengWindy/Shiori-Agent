from __future__ import annotations

import hashlib
import logging
import time
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, cast

from agent.core.passive_context import ContextStore
from agent.core.passive_reasoner import Reasoner
from agent.lifecycle.phase import Phase
from agent.lifecycle.phases.after_reasoning import (
    AfterReasoningFrame,
    default_after_reasoning_modules,
)
from agent.lifecycle.phases.after_turn import AfterTurnFrame, default_after_turn_modules
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
from agent.turns.outbound import OutboundDispatch, OutboundPort
from bus.event_bus import EventBus
from bus.events import InboundMessage, OutboundMessage
from core.common.diagnostic_log import diagnostic_context, diagnostic_line

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
    async def dispatch(self, outbound: OutboundDispatch) -> bool:
        return False


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
    before_turn_plugin_modules: list[object] | None = None
    before_reasoning_plugin_modules: list[object] | None = None
    before_step_plugin_modules: list[object] | None = None
    after_step_plugin_modules: list[object] | None = None
    after_reasoning_plugin_modules: list[object] | None = None
    after_turn_plugin_modules: list[object] | None = None


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

    def add_before_turn_plugin_modules(
        self,
        modules: list[object],
    ) -> None:
        self._passive_pipeline.add_before_turn_plugin_modules(modules)

    def add_before_reasoning_plugin_modules(
        self,
        modules: list[object],
    ) -> None:
        self._passive_pipeline.add_before_reasoning_plugin_modules(modules)

    def add_after_reasoning_plugin_modules(
        self,
        modules: list[object],
    ) -> None:
        self._passive_pipeline.add_after_reasoning_plugin_modules(modules)

    def add_after_turn_plugin_modules(
        self,
        modules: list[object],
    ) -> None:
        self._passive_pipeline.add_after_turn_plugin_modules(modules)

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
        add_before_step = getattr(self._reasoner, "add_before_step_plugin_modules", None)
        if add_before_step is not None:
            add_before_step(list(deps.before_step_plugin_modules or []))
        add_after_step = getattr(self._reasoner, "add_after_step_plugin_modules", None)
        if add_after_step is not None:
            add_after_step(list(deps.after_step_plugin_modules or []))
        self._outbound_port = deps.outbound_port or _NoopOutboundPort()
        self._history_window = deps.history_window
        self._memory_consolidator = deps.memory_consolidator
        self._before_turn_plugin_modules = list(deps.before_turn_plugin_modules or [])
        self._before_reasoning_plugin_modules = list(
            deps.before_reasoning_plugin_modules or []
        )
        self._after_reasoning_plugin_modules = list(
            deps.after_reasoning_plugin_modules or []
        )
        self._after_turn_plugin_modules = list(deps.after_turn_plugin_modules or [])
        bus = deps.event_bus or EventBus()
        self._bus = bus

        self._before_turn = self._build_before_turn_phase()
        self._before_reasoning = self._build_before_reasoning_phase()
        self._after_reasoning = self._build_after_reasoning_phase()
        self._after_turn = self._build_after_turn_phase()

    def add_before_turn_plugin_modules(
        self,
        modules: list[object],
    ) -> None:
        self._before_turn_plugin_modules.extend(modules)
        self._before_turn = self._build_before_turn_phase()

    def add_before_reasoning_plugin_modules(
        self,
        modules: list[object],
    ) -> None:
        self._before_reasoning_plugin_modules.extend(modules)
        self._before_reasoning = self._build_before_reasoning_phase()

    def add_after_reasoning_plugin_modules(
        self,
        modules: list[object],
    ) -> None:
        self._after_reasoning_plugin_modules.extend(modules)
        self._after_reasoning = self._build_after_reasoning_phase()

    def add_after_turn_plugin_modules(
        self,
        modules: list[object],
    ) -> None:
        self._after_turn_plugin_modules.extend(modules)
        self._after_turn = self._build_after_turn_phase()

    def _build_before_turn_phase(self) -> Phase[TurnState, BeforeTurnCtx, BeforeTurnFrame]:
        return Phase(
            default_before_turn_modules(
                self._bus,
                self._session.session_manager,
                self._context_store,
                keep_count=self._history_window,
                consolidator=self._memory_consolidator,
                plugin_modules=cast("list[Any]", self._before_turn_plugin_modules),
            ),
            frame_factory=BeforeTurnFrame,
        )

    def _build_before_reasoning_phase(
        self,
    ) -> Phase[BeforeReasoningInput, BeforeReasoningCtx, BeforeReasoningFrame]:
        return Phase(
            default_before_reasoning_modules(
                self._bus,
                self._tools,
                self._session.session_manager,
                self._context,
                plugin_modules=cast("list[Any]", self._before_reasoning_plugin_modules),
            ),
            frame_factory=BeforeReasoningFrame,
        )

    def _build_after_reasoning_phase(
        self,
    ) -> Phase[AfterReasoningInput, AfterReasoningResult, AfterReasoningFrame]:
        return Phase(
            default_after_reasoning_modules(
                self._bus,
                self._session,
                self._llm,
                self._llm_config,
                plugin_modules=cast("list[Any]", self._after_reasoning_plugin_modules),
            ),
            frame_factory=AfterReasoningFrame,
        )

    def _build_after_turn_phase(
        self,
    ) -> Phase[TurnSnapshot, OutboundMessage, AfterTurnFrame]:
        return Phase(
            default_after_turn_modules(
                self._bus,
                self._outbound_port,
                self._context,
                self._history_window,
                plugin_modules=cast("list[Any]", self._after_turn_plugin_modules),
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
        started = time.perf_counter()
        turn_id = _turn_log_id(key, msg)
        state = TurnState(
            msg=msg,
            session_key=key,
            dispatch_outbound=dispatch_outbound,
        )
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
                    before_turn = await self._before_turn.run(state)
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

                # Phase 3-4: Reasoning（BeforeStep/AfterStep 模块链在 Reasoner 内部执行）。
                session = state.session
                if session is None:
                    raise RuntimeError("Passive turn requires TurnState.session")
                with diagnostic_context(phase="reasoner"):
                    turn_result = await self._reasoner.run_turn(
                        msg=msg,
                        skill_names=list(before_reasoning.skill_names) or None,
                        session=session,
                        base_history=None,
                        retrieved_memory_block=before_reasoning.retrieved_memory_block,
                        extra_hints=list(before_reasoning.extra_hints) or None,
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
            except MemoryConsolidationFailedError:
                raise
            except Exception as exc:
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
                return await self._control_outbound(
                    state,
                    OutboundMessage(
                        channel=msg.channel,
                        chat_id=msg.chat_id,
                        content="处理消息时出错，请稍后再试。",
                    ),
                )

            try:
                # Phase 5: AfterReasoning 模块链（parse、AfterReasoning 事件、持久化、出站消息）。
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

            try:
                # Phase 6: AfterTurn 模块链（TurnCommitted fanout、AfterTurn fanout、dispatch）。
                with diagnostic_context(phase="after_turn"):
                    outbound = await self._after_turn.run(
                        TurnSnapshot(
                            state=state,
                            outbound=after_reasoning.outbound,
                            ctx=after_reasoning.ctx,
                        )
                    )
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
        after_reasoning = await self._after_reasoning.run(
            AfterReasoningInput(state=state, turn_result=turn_result)
        )
        return await self._after_turn.run(
            TurnSnapshot(
                state=state,
                outbound=after_reasoning.outbound,
                ctx=after_reasoning.ctx,
            )
        )

    # abort / 错误路径的统一 dispatch helper，只有 dispatch_outbound=True 时才发送。
    async def _control_outbound(
        self,
        state: TurnState,
        outbound: OutboundMessage,
    ) -> OutboundMessage:
        if state.dispatch_outbound:
            metadata = dict(state.msg.metadata or {})
            metadata.update(outbound.metadata or {})
            _ = await self._outbound_port.dispatch(
                OutboundDispatch(
                    channel=outbound.channel,
                    chat_id=outbound.chat_id,
                    content=outbound.content,
                    thinking=outbound.thinking,
                    metadata=metadata,
                    media=outbound.media,
                )
            )
        return outbound
