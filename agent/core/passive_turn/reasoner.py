from __future__ import annotations

import asyncio
import logging
from abc import ABC, abstractmethod
from datetime import datetime
from typing import TYPE_CHECKING, Any, Awaitable, Callable, cast

from .helpers import (
    build_turn_injection_prompt,
    extract_model_facing_turn,
    get_history_since_consolidated,
    get_session_metadata,
)
from .reasoning_loop import _PassiveReasoningLoopMixin
from .reasoning_result import _PassiveReasoningResultMixin
from agent.core.runtime_support import ToolDiscoveryState
from agent.core.types import ReasonerResult
from agent.lifecycle.phase import Phase
from agent.lifecycle.phases.after_step import AfterStepFrame, default_after_step_modules
from agent.lifecycle.phases.before_step import BeforeStepFrame, default_before_step_modules
from agent.lifecycle.phases.prompt_render import (
    PromptRenderFrame,
    default_prompt_render_modules,
)
from agent.lifecycle.types import (
    AfterStepCtx,
    BeforeStepCtx,
    BeforeStepInput,
    PromptRenderInput,
    PromptRenderResult,
)
from agent.prompting import DEFAULT_CONTEXT_TRIM_PLANS
from agent.provider import ContentSafetyError, ContextLengthError
from agent.tool_hooks import ToolExecutor
from agent.tools.tool_search import ToolSearchTool
from bus.event_bus import EventBus

if TYPE_CHECKING:
    from agent.context import ContextBuilder
    from agent.core.runtime_support import SessionLike, TurnRunResult
    from agent.looping.ports import LLMConfig, LLMServices
    from agent.tool_hooks.base import ToolHook
    from agent.tools.registry import ToolRegistry
    from session.manager import SessionManager

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
    ) -> ReasonerResult:
        """执行多轮 tool loop，并返回本轮结果。"""

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
    ) -> "TurnRunResult":
        """执行完整被动 turn，包括 retry / trim / tool loop。"""

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
        self._prompt_render_plugin_modules: list[object] = []
        self._before_step_plugin_modules: list[object] = []
        self._after_step_plugin_modules: list[object] = []
        # Direct reference to ToolSearchTool so we can pass excluded_names
        # explicitly instead of routing through the ContextVar side-channel.
        _ts = tools.get_tool("tool_search")
        self._tool_search_tool: ToolSearchTool | None = (
            _ts if isinstance(_ts, ToolSearchTool) else None
        )
        self._tool_executor = ToolExecutor([])
        self._stream_sink_factory: Callable[
            [object], Callable[[dict[str, str] | str], Awaitable[None]] | None
        ] | None = None
        bus = event_bus or EventBus()
        self._bus = bus
        self._before_step = self._build_before_step_phase()
        self._after_step = self._build_after_step_phase()
        self._prompt_render: Phase[
            PromptRenderInput,
            PromptRenderResult,
            PromptRenderFrame,
        ] | None = (
            self._build_prompt_render_phase(context)
            if context is not None
            else None
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

    def _build_after_step_phase(self) -> Phase[AfterStepCtx, AfterStepCtx, AfterStepFrame]:
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
        factory: Callable[
            [object], Callable[[dict[str, str] | str], Awaitable[None]] | None
        ]
        | None,
    ) -> None:
        self._stream_sink_factory = factory

    async def run_turn(
        self,
        *,
        msg,
        session: "SessionLike",
        skill_names: list[str] | None = None,
        base_history: list[dict] | None = None,
        retrieved_memory_block: str = "",
        extra_hints: list[str] | None = None,
    ) -> "TurnRunResult":
        from agent.core.runtime_support import TurnRunResult

        if self._context is None or self._session_manager is None:
            raise RuntimeError("DefaultReasoner.run_turn requires context and session_manager")
        if self._prompt_render is None:
            self._prompt_render = self._build_prompt_render_phase(self._context)

        # 1. 先准备 retry trace、history 和 preload 工具集合。
        retry_attempts: list[dict[str, object]] = []
        retry_trace: dict[str, object] = {
            "attempts": retry_attempts,
            "selected_plan": None,
            "trimmed_sections": [],
        }
        source_history = (
            base_history
            if base_history is not None
            else get_history_since_consolidated(session, self._memory_window)
        )
        total_history = len(source_history)
        preloaded: set[str] | None = None
        preloaded_order: list[str] = []
        if self._tool_search_enabled:
            preloaded_order = self._discovery.get_preloaded_ordered(session.key)
            preloaded = set(preloaded_order)
            logger.info(
                "[tool_search] LRU preloaded=%s",
                preloaded_order if preloaded_order else "[]",
            )
        stream_sink = (
            self._stream_sink_factory(msg) if self._stream_sink_factory is not None else None
        )
        disabled_tools = _disabled_tools_from_msg(msg)
        tool_execution_context = self._tools.get_context()

        # 2. 再按 trim plan + history window 顺序逐轮尝试。
        attempts = self._build_attempt_plans(total_history)
        for attempt, plan in enumerate(attempts):
            retry_attempts.append(
                {
                    "name": plan["name"],
                    "history_window": plan["history_window"],
                    "disabled_sections": sorted(plan["disabled_sections"]),
                }
            )
            history_for_attempt = self._slice_history(
                source_history,
                plan["history_window"],
            )
            turn_injection_prompt = build_turn_injection_prompt(
                tools=self._tools,
                tool_search_enabled=self._tool_search_enabled,
                visible_names=(
                    (preloaded or set()) | disabled_tools
                    if self._tool_search_enabled
                    else None
                ),
            )
            prompt_render = await self.render_prompt(
                PromptRenderInput(
                    session_key=session.key,
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
                    session_metadata=get_session_metadata(session),
                )
            )
            initial_messages = prompt_render.messages
            llm_user_content, llm_context_frame = extract_model_facing_turn(
                initial_messages
            )
            try:
                result = await self.run(
                    initial_messages,
                    request_time=msg.timestamp,
                    preloaded_tools=preloaded,
                    preloaded_tool_order=preloaded_order,
                    preflight_injected=True,
                    on_content_delta=stream_sink,
                    tool_event_session_key=session.key,
                    tool_event_channel=msg.channel,
                    tool_event_chat_id=msg.chat_id,
                    tool_execution_context=tool_execution_context,
                    disabled_tools=disabled_tools,
                )
                tools_used = list(result.metadata.get("tools_used") or [])
                tools_unlocked = list(result.metadata.get("tools_unlocked") or [])
                tool_chain = list(result.metadata.get("tool_chain") or [])
                if attempt > 0:
                    window = plan["history_window"]
                    retry_trace["selected_plan"] = plan["name"]
                    retry_trace["trimmed_sections"] = sorted(plan["disabled_sections"])
                    logger.warning(
                        "重试成功 plan=%s window=%d disabled=%s，修剪 session 历史",
                        plan["name"],
                        window,
                        sorted(plan["disabled_sections"]),
                    )
                    if window == 0:
                        session.messages.clear()
                    else:
                        session.messages = session.messages[-window:]
                    session.last_consolidated = 0
                    await self._session_manager.save_async(cast(Any, session))

                if self._tool_search_enabled and (tools_used or tools_unlocked):
                    self._discovery.update(
                        session.key,
                        [*tools_unlocked, *tools_used],
                        self._tools.get_always_on_names(),
                    )
                if attempt == 0:
                    retry_trace["selected_plan"] = plan["name"]
                    retry_trace["trimmed_sections"] = sorted(plan["disabled_sections"])
                if isinstance(llm_user_content, (str, list)):
                    retry_trace["llm_user_content"] = llm_user_content
                if isinstance(llm_context_frame, str) and llm_context_frame.strip():
                    retry_trace["llm_context_frame"] = llm_context_frame
                retry_trace["react_stats"] = dict(result.metadata.get("react_stats") or {})
                return TurnRunResult(
                    reply=result.reply,
                    tools_used=tools_used,
                    tool_chain=tool_chain,
                    thinking=result.thinking,
                    streamed=result.streamed,
                    context_retry=retry_trace,
                )
            except ContentSafetyError:
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
            except ContextLengthError:
                if attempt < len(attempts) - 1:
                    next_plan = attempts[attempt + 1]
                    logger.warning(
                        "上下文超长 (attempt=%d)，切到 plan=%s window=%d disabled=%s",
                        attempt + 1,
                        next_plan["name"],
                        next_plan["history_window"],
                        sorted(next_plan["disabled_sections"]),
                    )
                else:
                    logger.warning("上下文超长：所有窗口均失败，清空历史后仍超长")
                    return TurnRunResult(
                        reply="上下文过长无法处理，请尝试新建对话。",
                        context_retry=retry_trace,
                    )
            except asyncio.TimeoutError:
                logger.warning("LLM 流响应超时 (attempt=%d)，远端连接中断", attempt + 1)
                return TurnRunResult(
                    reply="模型流响应中断，请刷新对话重试。",
                    context_retry=retry_trace,
                )
        return TurnRunResult(reply="（安全重试异常）", context_retry=retry_trace)

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
