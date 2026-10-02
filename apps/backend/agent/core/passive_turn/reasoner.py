from __future__ import annotations

from core.common.message_source import MessageSource
from agent.tools.turn_scope import tool_turn
from agent.account_delivery.turn_state import account_delivery_scope

from core.roles.reply_state import role_mood_catalog
from core.common.channel_chat_types import is_group_chat_type

import asyncio
import logging
import time
from abc import ABC, abstractmethod
from datetime import datetime
from copy import deepcopy

from core.compaction import (
    CompactionController,
    CompactionPolicy,
    CompactionFailedError,
    CompactionResult,
)
from core.compaction_summary import WorkingSummaryWriter
from session.maintenance_progress import window_key
from .compaction_render import CompactionRenderer
from .context_window import ContextWindow
from .compaction import (
    RequestCompaction,
    request_compaction_scope,
    with_working_summary,
)
from typing import TYPE_CHECKING, Any, Awaitable, Callable, cast

from .helpers import (
    build_turn_injection_prompt,
    extract_model_facing_turn,
    get_window_history,
    get_window_preloaded_tools,
    get_session_metadata,
    get_window_sources,
)
from agent.prompting.usage_anchor import turn_usage_context
from agent.prompting.listening_block import HeardLine, turn_heard
from .reasoning_loop import _PassiveReasoningLoopMixin
from .reasoning_result import _PassiveReasoningResultMixin
from agent.core.runtime_support import ToolDiscoveryState
from agent.core.types import ReasonerResult
from agent.lifecycle.phase import Phase
from agent.lifecycle.phases.after_step import AfterStepFrame, default_after_step_modules
from agent.lifecycle.phases.before_step import (
    BeforeStepFrame,
    default_before_step_modules,
)
from agent.lifecycle.phases.prompt_render import (
    PromptRenderFrame,
    default_prompt_render_modules,
)
from agent.lifecycle.types import (
    inbound_thread_id,
    AfterStepCtx,
    BeforeStepCtx,
    BeforeStepInput,
    PromptRenderInput,
    PromptRenderResult,
)
from agent.prompting import DEFAULT_CONTEXT_TRIM_PLANS
from agent.provider import ContentSafetyError, ContextLengthError, LLMProvider
from agent.tool_hooks import ToolExecutor
from agent.tools.external_access import external_tools_restricted
from bus.event_bus import EventBus

if TYPE_CHECKING:
    from agent.context import ContextBuilder
    from agent.core.runtime_support import SessionLike, TurnRunResult
    from agent.looping.ports import LLMConfig, LLMServices
    from agent.tool_hooks.base import ToolHook
    from agent.tools.registry import ToolRegistry
    from conversation.context_scope import ContextView
    from session.manager import SessionManager
    from core.memory.markdown import MarkdownMemoryMaintenance

logger = logging.getLogger("agent.core.passive_turn")

_SAFETY_RETRY_RATIOS = (1.0, 0.5, 0.0)


def _disabled_tools_from_msg(msg: object) -> set[str]:
    metadata: object = getattr(msg, "metadata", None)
    if not isinstance(metadata, dict):
        return set()
    raw = metadata.get("disabled_tools")
    if isinstance(raw, str):
        return {raw} if raw else set()
    if isinstance(raw, (list, tuple, set)):
        return {str(item) for item in raw if str(item)}
    return set()


class Reasoner(ABC):

    @abstractmethod
    async def run(
        self,
        initial_messages: list[dict],
        *,
        request_time: datetime | None = None,
        preloaded_tools: set[str] | None = None,
        preloaded_tool_order: list[str] | None = None,
        preflight_injected: bool = True,
        on_content_delta: Callable[[dict[str, str]], Awaitable[None]] | None = None,
        tool_event_session_key: str = "",
        tool_event_channel: str = "",
        tool_event_chat_id: str = "",
        tool_execution_context: dict[str, Any] | None = None,
        disabled_tools: set[str] | None = None,
        external_restricted: bool = False,
    ) -> ReasonerResult:
        """执行多轮 tool loop，并返回本轮结果。

        ``external_restricted`` 为真时只能使用外部上下文允许的工具（#489）。
        """

    @abstractmethod
    async def run_turn(
        self,
        *,
        msg,
        session: "SessionLike",
        skill_names: list[str] | None = None,
        base_history: list[dict] | None = None,
        retrieved_memory_block: str = "",
        extra_hints: list[str] | None = None,
        context_view: "ContextView | None" = None,
    ) -> "TurnRunResult":
        """执行完整被动 turn，包括 retry / trim / tool loop。

        ``context_view`` 限定从会话读取的历史只含回合所在上下文的消息。
        """

    def add_tool_hooks(self, hooks: list["ToolHook"]) -> None:
        """子类可重写以注入 tool hooks。默认 no-op。"""

    def add_prompt_render_plugin_modules(
        self,
        modules: list[object],
    ) -> None:
        """子类可重写以注入 prompt render modules。默认 no-op。"""

    def add_before_step_plugin_modules(
        self,
        modules: list[object],
    ) -> None:
        """子类可重写以注入 before-step modules。默认 no-op。"""

    def add_after_step_plugin_modules(
        self,
        modules: list[object],
    ) -> None:
        """子类可重写以注入 after-step modules。默认 no-op。"""

    async def render_prompt(
        self,
        input: PromptRenderInput,
    ) -> PromptRenderResult:
        raise NotImplementedError


class DefaultReasoner(
    _PassiveReasoningLoopMixin,
    _PassiveReasoningResultMixin,
    Reasoner,
):
    """执行 prompt 渲染、安全重试与多轮工具推理。"""

    def __init__(
        self,
        llm: "LLMServices",
        llm_config: "LLMConfig",
        tools: "ToolRegistry",
        discovery: ToolDiscoveryState,
        *,
        tool_search_enabled: bool,
        memory_window: int,
        context: "ContextBuilder | None" = None,
        session_manager: "SessionManager | None" = None,
        event_bus: "EventBus | None" = None,
        compaction_memory: MarkdownMemoryMaintenance | None = None,
    ) -> None:
        self._llm = llm
        self._llm_config = llm_config
        self._tools = tools
        self._discovery = discovery
        self._tool_search_enabled = tool_search_enabled
        self._memory_window = memory_window
        self._context = context
        self._session_manager = session_manager
        self._event_bus = event_bus
        self._compaction = (
            CompactionController(
                session_manager,
                compaction_memory,
                WorkingSummaryWriter(
                    session_manager,
                    llm.provider,
                    llm_config.model,
                    llm_config.max_tokens,
                ),
            )
            if session_manager is not None and compaction_memory is not None
            else None
        )
        self._prompt_render_plugin_modules: list[object] = []
        self.context_window = (
            ContextWindow(
                session_manager,
                self._compaction,
                llm.provider,
                llm_config,
                tools,
                self.render_prompt,
            )
            if session_manager is not None and self._compaction is not None
            else None
        )
        self._before_step_plugin_modules: list[object] = []
        self._after_step_plugin_modules: list[object] = []
        self._tool_executor = ToolExecutor([])
        self._stream_sink_factory: (
            Callable[[object], Callable[[dict[str, str] | str], Awaitable[None]] | None]
            | None
        ) = None
        bus = event_bus or EventBus()
        self._bus = bus
        self._before_step = self._build_before_step_phase()
        self._after_step = self._build_after_step_phase()
        self._prompt_render: (
            Phase[
                PromptRenderInput,
                PromptRenderResult,
                PromptRenderFrame,
            ]
            | None
        ) = (
            self._build_prompt_render_phase(context) if context is not None else None
        )

    def add_tool_hooks(self, hooks: list["ToolHook"]) -> None:
        self._tool_executor.add_hooks(hooks)

    def add_prompt_render_plugin_modules(
        self,
        modules: list[object],
    ) -> None:
        self._prompt_render_plugin_modules.extend(modules)
        if self._context is not None:
            self._prompt_render = self._build_prompt_render_phase(self._context)

    def add_before_step_plugin_modules(
        self,
        modules: list[object],
    ) -> None:
        self._before_step_plugin_modules.extend(modules)
        self._before_step = self._build_before_step_phase()

    def add_after_step_plugin_modules(
        self,
        modules: list[object],
    ) -> None:
        self._after_step_plugin_modules.extend(modules)
        self._after_step = self._build_after_step_phase()

    def _build_before_step_phase(
        self,
    ) -> Phase[BeforeStepInput, BeforeStepCtx, BeforeStepFrame]:
        return Phase(
            default_before_step_modules(
                self._bus,
                plugin_modules=cast("list[Any]", self._before_step_plugin_modules),
            ),
            frame_factory=BeforeStepFrame,
        )

    def _build_after_step_phase(
        self,
    ) -> Phase[AfterStepCtx, AfterStepCtx, AfterStepFrame]:
        return Phase(
            default_after_step_modules(
                self._bus,
                plugin_modules=cast("list[Any]", self._after_step_plugin_modules),
            ),
            frame_factory=AfterStepFrame,
        )

    def _build_prompt_render_phase(
        self,
        context: "ContextBuilder",
    ) -> Phase[PromptRenderInput, PromptRenderResult, PromptRenderFrame]:
        return Phase(
            default_prompt_render_modules(
                self._bus,
                context,
                plugin_modules=cast("list[Any]", self._prompt_render_plugin_modules),
            ),
            frame_factory=PromptRenderFrame,
        )

    async def render_prompt(
        self,
        input: PromptRenderInput,
    ) -> PromptRenderResult:
        if self._context is None:
            raise RuntimeError("DefaultReasoner.render_prompt requires context")
        if self._prompt_render is None:
            self._prompt_render = self._build_prompt_render_phase(self._context)
        return await self._prompt_render.run(input)

    def set_stream_sink_factory(
        self,
        factory: (
            Callable[[object], Callable[[dict[str, str] | str], Awaitable[None]] | None]
            | None
        ),
    ) -> None:
        self._stream_sink_factory = factory

    @tool_turn
    @turn_usage_context
    async def run_turn(
        self,
        *,
        msg,
        session: "SessionLike",
        skill_names: list[str] | None = None,
        base_history: list[dict] | None = None,
        retrieved_memory_block: str = "",
        extra_hints: list[str] | None = None,
        context_view: "ContextView | None" = None,
    ) -> "TurnRunResult":
        from agent.core.runtime_support import TurnRunResult

        if self._context is None or self._session_manager is None:
            raise RuntimeError(
                "DefaultReasoner.run_turn requires context and session_manager"
            )
        if self._prompt_render is None:
            self._prompt_render = self._build_prompt_render_phase(self._context)

        # The model and policy are execution snapshots, before any history render.
        policy = CompactionPolicy(self._llm_config.compaction_retained_turns)
        message_limit = len(session.messages)
        provider = self._llm.provider
        if self._compaction is not None and isinstance(provider, LLMProvider):
            await self._session_manager.bind_window_request(
                session.key,
                context_view,
                provider.context_identity(self._llm_config.model),
            )
        snapshot = self._session_manager.window_snapshot(
            session.key, context_view, message_limit=message_limit
        )
        progress = snapshot.maintenance_progress
        assert progress is not None
        window_id = window_key(context_view)
        protected_current: dict | None = None
        compaction_results: list[dict] = []

        # 1. 先准备 retry trace、history 和 preload 工具集合。
        turn_started_at = time.perf_counter()
        first_content_at: float | None = None
        retry_attempts: list[dict[str, object]] = []
        retry_trace: dict[str, object] = {
            "attempts": retry_attempts,
            "selected_plan": None,
            "trimmed_sections": [],
        }
        source_history = (
            base_history
            if base_history is not None
            else get_window_history(snapshot, self._memory_window, context_view)
        )
        total_history = len(source_history)
        stream_sink = (
            self._stream_sink_factory(msg)
            if self._stream_sink_factory is not None
            else None
        )
        measured_stream_sink = stream_sink
        if stream_sink is not None:

            async def _measure_stream_delta(delta: dict[str, str] | str) -> None:
                nonlocal first_content_at
                payload = {"content_delta": delta} if isinstance(delta, str) else delta
                if payload.get("content_delta") and first_content_at is None:
                    first_content_at = time.perf_counter()
                await stream_sink(delta)

            measured_stream_sink = _measure_stream_delta
        disabled_tools = _disabled_tools_from_msg(msg)
        # 外部上下文里非用户本人发起的回合只能用允许集合内的工具（#489）。
        external_restricted = external_tools_restricted(
            context_view, MessageSource.from_inbound(msg)
        )
        tool_execution_context = self._tools.get_context()
        account_delivery_state: dict[str, bool] = {}
        role_metadata = get_session_metadata(session)
        previous_mood_updated_at = str(role_metadata.get("current_mood_updated_at", ""))

        # 2. 安全审查重试保留既有裁剪；预算压力只由统一控制器处理。
        attempts = self._build_attempt_plans(total_history)
        for attempt, plan in enumerate(attempts):
            if attempt:
                snapshot = self._session_manager.window_snapshot(
                    session.key,
                    context_view,
                    message_limit=message_limit,
                    expected=progress,
                )
                refreshed = snapshot.maintenance_progress
                assert refreshed is not None
                if base_history is None or refreshed.window_versions.get(
                    window_id, 0
                ) != progress.window_versions.get(window_id, 0):
                    source_history = get_window_history(
                        snapshot, self._memory_window, context_view
                    )
            current_progress = snapshot.maintenance_progress
            assert current_progress is not None
            working_summary = current_progress.summaries.get(window_id, "")
            history_window = min(plan["history_window"], len(source_history))
            # 与历史同一窗口里非用户本人消息的来源，加上本群旁听块里的（#539），
            # 外部回合据此注入成员档案（#498）。
            window_sources = get_window_sources(
                snapshot,
                self._memory_window,
                context_view,
                self._heard_for_turn(context_view),
            )
            preloaded: set[str] | None = None
            preloaded_order: list[str] = []
            if self._tool_search_enabled:
                # 历史窗口里用过或解锁过的工具继续可见，直到窗口维护移出原文。
                preloaded_order = get_window_preloaded_tools(
                    snapshot,
                    self._memory_window,
                    context_view,
                    self._tools,
                )
                preloaded = set(preloaded_order)
                logger.info(
                    "[tool_search] history preloaded=%s",
                    preloaded_order if preloaded_order else "[]",
                )
            retry_attempts.append(
                {
                    "name": plan["name"],
                    "history_window": history_window,
                    "disabled_sections": sorted(plan["disabled_sections"]),
                }
            )
            # 重试只裁剪请求上下文，保留完整会话历史和记忆整合位置。
            history_for_attempt = self._slice_history(
                source_history,
                history_window,
            )
            turn_injection_prompt = build_turn_injection_prompt(
                tools=self._tools,
                tool_search_enabled=self._tool_search_enabled,
                visible_names=(
                    (preloaded or set()) | disabled_tools
                    if self._tool_search_enabled
                    else None
                ),
                external_only=external_restricted,
            )
            render_input = PromptRenderInput(
                session_key=session.key,
                message_source=MessageSource.from_inbound(msg),
                channel=msg.channel,
                chat_id=msg.chat_id,
                content=msg.content,
                media=msg.media if msg.media else None,
                timestamp=msg.timestamp,
                history=history_for_attempt,
                skill_names=skill_names,
                retrieved_memory_block=retrieved_memory_block,
                disabled_sections=plan["disabled_sections"],
                turn_injection_prompt=turn_injection_prompt,
                extra_hints=extra_hints,
                session_metadata=get_session_metadata(snapshot),
                context_scope=(
                    context_view.scope if context_view is not None else None
                ),
                thread_id=inbound_thread_id(msg),
                window_sources=window_sources,
            )
            prompt_render = await self.render_prompt(render_input)
            if protected_current is None:
                protected_current = deepcopy(prompt_render.messages[-1])
            elif protected_current.get("role") == "user":
                # A fresh window must not reread or replace this execution's input.
                prompt_render.messages[-1] = deepcopy(protected_current)
            initial_messages = with_working_summary(
                prompt_render.messages, working_summary
            )

            renderer = CompactionRenderer(
                self._session_manager,
                context_view,
                message_limit,
                render_input,
                deepcopy(protected_current),
                self.render_prompt,
                self._tools,
                self._tool_search_enabled,
                disabled_tools,
                external_restricted,
                lambda: self._heard_for_turn(context_view),
            )
            request_prefix_length = len(initial_messages)
            compaction = (
                RequestCompaction(
                    self._compaction,
                    session.key,
                    context_view,
                    policy,
                    message_limit,
                    request_prefix_length,
                    renderer.render,
                    renderer.history_tools,
                    results=compaction_results,
                )
                if self._compaction is not None
                else None
            )
            llm_user_content, llm_context_frame = extract_model_facing_turn(
                initial_messages
            )
            try:
                with (
                    account_delivery_scope(account_delivery_state),
                    request_compaction_scope(compaction),
                ):
                    result = await self.run(
                        initial_messages,
                        request_time=msg.timestamp,
                        preloaded_tools=preloaded,
                        preloaded_tool_order=preloaded_order,
                        preflight_injected=True,
                        on_content_delta=measured_stream_sink,
                        tool_event_session_key=session.key,
                        tool_event_channel=msg.channel,
                        tool_event_chat_id=msg.chat_id,
                        tool_execution_context=tool_execution_context,
                        disabled_tools=disabled_tools,
                        external_restricted=external_restricted,
                        reply_moods=(
                            role_mood_catalog(
                                role_metadata.get("role_runtime_config") or {}
                            )
                            if role_metadata.get("role_id")
                            else None
                        ),
                        group_reply=is_group_chat_type(msg.metadata.get("chat_type")),
                        previous_mood=str(role_metadata.get("current_mood") or ""),
                        previous_thought=str(
                            role_metadata.get("current_thought") or ""
                        ),
                    )
                tools_used = list(result.metadata.get("tools_used") or [])
                tool_chain = list(result.metadata.get("tool_chain") or [])
                retry_trace["selected_plan"] = plan["name"]
                retry_trace["trimmed_sections"] = sorted(plan["disabled_sections"])
                if attempt > 0:
                    logger.warning(
                        "重试成功 plan=%s window=%d disabled=%s",
                        plan["name"],
                        plan["history_window"],
                        sorted(plan["disabled_sections"]),
                    )

                retry_trace["request_usage"] = result.metadata.get("request_usage", {})
                if compaction is not None:
                    retry_trace["compaction"] = compaction.results
                if isinstance(llm_user_content, (str, list)):
                    retry_trace["llm_user_content"] = llm_user_content
                if isinstance(llm_context_frame, str) and llm_context_frame.strip():
                    retry_trace["llm_context_frame"] = llm_context_frame
                retry_trace["react_stats"] = dict(
                    result.metadata.get("react_stats") or {}
                )
                if "reply_recovery" in result.metadata:
                    retry_trace["reply_recovery"] = result.metadata["reply_recovery"]
                if account_delivery_state.get("sent"):
                    retry_trace["account_delivery_sent"] = True
                thinking_finished_at = first_content_at or time.perf_counter()
                turn_metrics: dict[str, int] = {
                    "thinking_duration_ms": max(
                        0,
                        int((thinking_finished_at - turn_started_at) * 1000),
                    )
                }
                total_tokens = retry_trace["react_stats"].get("total_tokens")
                if isinstance(total_tokens, int) and total_tokens >= 0:
                    turn_metrics["total_tokens"] = total_tokens
                retry_trace["turn_metrics"] = turn_metrics
                if role_metadata.get("role_id"):
                    retry_trace["formal_role_reply"] = True
                    retry_trace["role_reply_previous_updated_at"] = (
                        previous_mood_updated_at
                    )
                return TurnRunResult(
                    reply=result.reply,
                    tools_used=tools_used,
                    tool_chain=tool_chain,
                    thinking=result.thinking,
                    streamed=result.streamed,
                    context_retry=retry_trace,
                    # Kept off `context_retry`: that dict is snapshotted verbatim
                    # into persisted message/outbound metadata (JSON-only).
                    role_reply=result.metadata.get("role_reply"),
                    role_reply_mood_fresh=bool(
                        result.metadata.get("role_reply_mood_fresh")
                    ),
                )
            except ContentSafetyError:
                prefix_length = (
                    compaction.prefix_length if compaction else request_prefix_length
                )
                if any(
                    message.get("tool_calls")
                    for message in initial_messages[prefix_length:]
                ):
                    # Restarting a speaking attempt would execute its tools again.
                    raise
                if attempt < len(attempts) - 1:
                    next_plan = attempts[attempt + 1]
                    logger.warning(
                        "安全拦截 (attempt=%d)，切到 plan=%s window=%d disabled=%s",
                        attempt + 1,
                        next_plan["name"],
                        next_plan["history_window"],
                        sorted(next_plan["disabled_sections"]),
                    )
                else:
                    logger.warning("安全拦截：所有窗口均失败，当前消息本身可能违规")
                    return TurnRunResult(
                        reply="你的消息触发了安全审查，无法处理。",
                        context_retry=retry_trace,
                    )
            except ContextLengthError as exc:
                # A provider rejection after tools must never replay the entire turn.
                raise CompactionFailedError(
                    CompactionResult(
                        failure_stage="provider",
                        error=str(exc),
                        reason="provider_context_length",
                        memory_committed=(
                            any(item["memory_committed"] for item in compaction.results)
                            if compaction
                            else False
                        ),
                    )
                ) from exc
            except asyncio.TimeoutError:
                logger.warning("LLM 流响应超时 (attempt=%d)，远端连接中断", attempt + 1)
                return TurnRunResult(
                    reply="模型流响应中断，请刷新对话重试。",
                    context_retry=retry_trace,
                )
        return TurnRunResult(reply="（安全重试异常）", context_retry=retry_trace)

    def _heard_for_turn(self, context_view: "ContextView | None") -> list[HeardLine]:
        """外部回合所在会话旁听块里的消息；用户上下文回合没有旁听。"""
        if self._session_manager is None:
            raise RuntimeError("DefaultReasoner 读取旁听前文需要 session_manager")
        return turn_heard(self._session_manager, context_view)

    @staticmethod
    def _slice_history(source_history: list[dict], window: int) -> list[dict]:
        total_history = len(source_history)
        if window <= 0:
            return []
        if window >= total_history:
            return source_history
        return source_history[-window:]

    @staticmethod
    def _build_attempt_plans(total_history: int) -> list[dict]:
        attempts: list[dict] = []
        seen: set[tuple[tuple[str, ...], int]] = set()
        full_window = int(total_history * _SAFETY_RETRY_RATIOS[0])
        for trim_plan in DEFAULT_CONTEXT_TRIM_PLANS:
            disabled = set(trim_plan.drop_sections)
            key = (tuple(sorted(disabled)), full_window)
            if key in seen:
                continue
            seen.add(key)
            attempts.append(
                {
                    "name": trim_plan.name,
                    "disabled_sections": disabled,
                    "history_window": full_window,
                }
            )

        last_trim = set(DEFAULT_CONTEXT_TRIM_PLANS[-1].drop_sections)
        for ratio in _SAFETY_RETRY_RATIOS[1:]:
            window = int(total_history * ratio)
            key = (tuple(sorted(last_trim)), window)
            if key in seen:
                continue
            seen.add(key)
            attempts.append(
                {
                    "name": f"{DEFAULT_CONTEXT_TRIM_PLANS[-1].name}_history",
                    "disabled_sections": set(last_trim),
                    "history_window": window,
                }
            )
        return attempts

    @staticmethod
    def format_request_time_anchor(ts: datetime | None) -> str:
        # 1. 空时间戳时，使用当前本地时间。
        if ts is None:
            ts = datetime.now().astimezone()
        elif ts.tzinfo is None:
            ts = ts.astimezone()

        # 2. 输出稳定的 request_time 锚点字符串。
        return f"request_time={ts.isoformat()} ({ts.strftime('%Y-%m-%d %H:%M:%S %Z')})"
