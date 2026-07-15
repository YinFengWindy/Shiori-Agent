"""AgentLoop 主循环与消息处理。"""

from __future__ import annotations

import asyncio
import time
from datetime import datetime

from core.error_context import current_session_key
from ..interrupt import (
    TurnInterruptState,
)
from bus.events import (
    InboundItem,
    InboundMessage,
    OutboundMessage,
)
from bus.processing import ProcessingState

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from agent.tool_hooks.base import ToolHook

from .helpers import (
    _item_content,
    logger,
)

class _ProcessingMixin:
    async def run(self) -> None:
        self._running = True
        logger.info(f"AgentLoop 启动  max_iter={self.max_iterations}")
        while self._running:
            try:
                item = await asyncio.wait_for(self.bus.consume_inbound(), timeout=1.0)
            except asyncio.TimeoutError:
                continue

            key = item.session_key
            self._active_turn_states[key] = self._build_initial_turn_state(item, key)
            task = asyncio.create_task(self._process_role_scoped(item, key))
            self._active_tasks[key] = task
            try:
                await task
            except asyncio.CancelledError:
                logger.info(f"Turn cancelled for {key}")
            except Exception as e:
                logger.error(f"处理消息出错: {e}", exc_info=True)
                error_metadata = dict(getattr(item, "metadata", {}) or {})
                await self.bus.publish_outbound(
                    OutboundMessage(
                        channel=item.channel,
                        chat_id=item.chat_id,
                        content=f"出错：{e}",
                        metadata=error_metadata,
                    )
                )
            finally:
                self._active_tasks.pop(key, None)
                self._active_turn_states.pop(key, None)

    @property
    def processing_state(self) -> ProcessingState | None:
        return self._processing_state

    @property
    def role_world_registry(self):
        """Returns the registry used by direct turns and role-owned background work."""

        return self._role_world_registry

    @property
    def active_turn_states(self) -> dict[str, TurnInterruptState]:
        return self._active_turn_states

    def stop(self) -> None:
        self._running = False
        logger.info("AgentLoop 停止")

    def add_tool_hooks(self, hooks: list["ToolHook"]) -> None:
        self._reasoner.add_tool_hooks(hooks)

    def add_before_turn_plugin_modules(
        self,
        modules: list[object],
    ) -> None:
        self._agent_core.add_before_turn_plugin_modules(modules)

    def add_before_reasoning_plugin_modules(
        self,
        modules: list[object],
    ) -> None:
        self._agent_core.add_before_reasoning_plugin_modules(modules)

    def add_after_reasoning_plugin_modules(
        self,
        modules: list[object],
    ) -> None:
        self._agent_core.add_after_reasoning_plugin_modules(modules)

    def add_after_turn_plugin_modules(
        self,
        modules: list[object],
    ) -> None:
        self._agent_core.add_after_turn_plugin_modules(modules)

    def add_prompt_render_plugin_modules(
        self,
        modules: list[object],
    ) -> None:
        self._reasoner.add_prompt_render_plugin_modules(modules)

    def add_before_step_plugin_modules(
        self,
        modules: list[object],
    ) -> None:
        self._reasoner.add_before_step_plugin_modules(modules)

    def add_after_step_plugin_modules(
        self,
        modules: list[object],
    ) -> None:
        self._reasoner.add_after_step_plugin_modules(modules)

    # ── 中断控制面 ────────────────────────────────────────────────

    async def _process(
        self,
        msg: InboundItem,
        session_key: str | None = None,
        dispatch_outbound: bool = True,
    ) -> OutboundMessage:
        started = time.time()
        key = session_key or msg.session_key
        # 给本 turn task 打上 session 归属，供 observe 全局错误采集关联。
        _ = current_session_key.set(key)

        # 1. 先处理可能存在的续跑态，并发布 turn started。
        msg, resumed_from_interrupt = self._resume_interrupted_message(msg, key)
        await self._observe_turn_started(msg, key)
        content = _item_content(msg)
        preview = content[:60] + "..." if len(content) > 60 else content
        logger.info(f"Processing message from {msg.channel}: {preview}")

        # 2. 再进入 busy 状态并执行核心处理。
        if self._processing_state:
            self._processing_state.enter(key)
        try:
            outbound = await self._core_runner.process(
                msg,
                key,
                dispatch_outbound=dispatch_outbound,
            )
            if resumed_from_interrupt:
                self._interrupt_states.pop(key, None)
            return outbound
        finally:
            # 3. 最后无论成功失败都直接释放 busy 状态。
            if self._processing_state:
                self._processing_state.exit(key)
            _ = started

    async def _process_role_scoped(
        self,
        item: InboundItem,
        session_key: str,
        *,
        dispatch_outbound: bool = True,
    ) -> OutboundMessage:
        """Dispatches role-bound messages through their owning world before a turn."""

        registry = getattr(self, "_role_world_registry", None)
        metadata = getattr(item, "metadata", None)
        if registry is None or not isinstance(metadata, dict):
            return await self._process(
                item,
                session_key=session_key,
                dispatch_outbound=dispatch_outbound,
            )
        context = registry.context_from_metadata(metadata)
        if context is None:
            if str(metadata.get("role_id") or "").strip() or session_key.startswith("role:"):
                raise ValueError("角色回合缺少完整 RoleExecutionContext")
            return await self._process(
                item,
                session_key=session_key,
                dispatch_outbound=dispatch_outbound,
            )
        operation = lambda: self._process(
            item,
            session_key=session_key,
            dispatch_outbound=dispatch_outbound,
        )
        if context.work_kind == "scheduled_job":
            return await registry.dispatch_background_task(context, operation)
        return await registry.dispatch_passive_turn(context, operation)

    async def process_direct(
        self,
        content: str,
        session_key: str = "cli:direct",
        channel: str = "cli",
        chat_id: str = "direct",
        omit_user_turn: bool = False,
        skip_post_memory: bool = False,
        skip_memory_retrieval: bool = False,
        stream_events: bool = False,
        disabled_tools: list[str] | None = None,
        media: list[str] | None = None,
        metadata: dict[str, object] | None = None,
    ) -> str:
        merged_metadata: dict[str, object] = dict(metadata or {})
        role_id = str(merged_metadata.get("role_id") or "").strip()
        if role_id and hasattr(self, "session_manager"):
            session_key = self.session_manager.role_session_key(role_id)
            merged_metadata["session_key_override"] = session_key
        self._ensure_direct_role_context(
            merged_metadata,
            session_key=session_key,
            channel=channel,
            chat_id=chat_id,
        )
        if omit_user_turn:
            merged_metadata["omit_user_turn"] = True
        if skip_post_memory:
            merged_metadata["skip_post_memory"] = True
        if skip_memory_retrieval:
            merged_metadata["skip_memory_retrieval"] = True
        if not stream_events:
            merged_metadata["suppress_stream_events"] = True
        if disabled_tools:
            merged_metadata["disabled_tools"] = list(disabled_tools)
        msg = InboundMessage(
            channel=channel,
            sender="user",
            chat_id=chat_id,
            content=content,
            media=list(media or []),
            metadata=merged_metadata,
        )
        key = session_key
        self._active_turn_states[key] = self._build_initial_turn_state(msg, key)
        task = asyncio.create_task(
            self._process_role_scoped(
                msg,
                session_key=key,
                dispatch_outbound=False,
            ),
            name=f"agent_loop_direct:{key}",
        )
        self._active_tasks[key] = task
        try:
            response = await task
            return response.content if response else ""
        finally:
            if self._active_tasks.get(key) is task:
                self._active_tasks.pop(key, None)
                self._active_turn_states.pop(key, None)

    def _ensure_direct_role_context(
        self,
        metadata: dict[str, object],
        *,
        session_key: str,
        channel: str,
        chat_id: str,
    ) -> None:
        """Adds a role context to direct entrypoints backed by a formal role session."""

        registry = getattr(self, "_role_world_registry", None)
        if registry is None or registry.context_from_metadata(metadata) is not None:
            return
        session = self.session_manager.get_or_create(session_key)
        session_metadata = session.metadata if isinstance(session.metadata, dict) else {}
        role_id = str(metadata.get("role_id") or session_metadata.get("role_id") or "").strip()
        thread_id = str(metadata.get("thread_id") or "").strip()
        transport_channel = str(metadata.get("transport_channel") or "").strip()
        transport_chat_id = str(metadata.get("transport_chat_id") or "").strip()
        if not role_id:
            return
        if not all((thread_id, transport_channel, transport_chat_id)):
            raise ValueError("角色直连回合缺少完整 RoleExecutionContext")
        context = registry.create_context(
            role_id=role_id,
            thread_id=thread_id,
            transport_channel=transport_channel,
            transport_chat_id=transport_chat_id,
            source=str(
                metadata.get("role_source")
                or metadata.get("source")
                or "direct_role_session"
            ),
            work_kind=str(metadata.get("role_work_kind") or "passive_turn"),
            request_id=str(metadata.get("request_id") or ""),
            delivery_key=str(metadata.get("delivery_key") or ""),
        )
        metadata.update(context.to_metadata())

    async def run_role_operation(self, metadata: dict[str, str], operation):
        """Runs non-turn role work through the world's thread execution boundary."""

        registry = self._role_world_registry
        if registry is None:
            raise RuntimeError("RoleWorldRegistry 未配置")
        context = registry.context_from_metadata(metadata)
        if context is None:
            role_id = str(metadata.get("role_id") or "").strip()
            thread_id = str(metadata.get("thread_id") or "").strip()
            transport_channel = str(metadata.get("transport_channel") or "").strip()
            transport_chat_id = str(metadata.get("transport_chat_id") or "").strip()
            if not all((role_id, thread_id, transport_channel, transport_chat_id)):
                raise ValueError("后台任务缺少完整 RoleExecutionContext")
            context = registry.create_context(
                role_id=role_id,
                thread_id=thread_id,
                transport_channel=transport_channel,
                transport_chat_id=transport_chat_id,
                source=str(metadata.get("role_source") or "scheduler"),
                work_kind=str(metadata.get("role_work_kind") or "scheduled_job"),
                request_id=str(metadata.get("request_id") or ""),
                delivery_key=str(metadata.get("delivery_key") or ""),
            )
        return await registry.dispatch_background_task(context, operation)

    async def _run_agent_loop(
        self,
        initial_messages: list[dict],
        request_time: datetime | None = None,
        preloaded_tools: set[str] | None = None,
        tool_event_session_key: str = "",
        tool_event_channel: str = "",
        tool_event_chat_id: str = "",
        tool_execution_context: dict[str, str] | None = None,
    ) -> tuple[str, list[str], list[dict], set[str] | None, str | None]:
        from agent.core.passive_turn import build_turn_injection_prompt
        from agent.prompting import (
            PromptSectionRender,
            build_context_frame_content,
            build_context_frame_message,
        )

        # 1. 补充 deferred tools hint（与 run_turn 路径保持一致）。
        visible = preloaded_tools if self._tool_search_enabled else None
        hint = build_turn_injection_prompt(
            tools=self.tools,
            tool_search_enabled=self._tool_search_enabled,
            visible_names=visible,
        )
        if hint:
            hint_message = build_context_frame_message(
                build_context_frame_content(
                    [
                        PromptSectionRender(
                            name="turn_injection",
                            content=hint,
                            is_static=False,
                        )
                    ]
                )
            )
            if initial_messages and initial_messages[-1].get("role") == "user":
                initial_messages = initial_messages[:-1] + [
                    hint_message,
                    initial_messages[-1],
                ]
            else:
                initial_messages = initial_messages + [hint_message]

        # 2. 内部事件链统一直接走新 Reasoner。
        result = await self._reasoner.run(
            initial_messages,
            request_time=request_time,
            preloaded_tools=preloaded_tools,
            preflight_injected=True,
            tool_event_session_key=tool_event_session_key,
            tool_event_channel=tool_event_channel,
            tool_event_chat_id=tool_event_chat_id,
            tool_execution_context=tool_execution_context,
        )
        tools_used = list(result.metadata.get("tools_used") or [])
        tool_chain = list(result.metadata.get("tool_chain") or [])
        visible_names = result.metadata.get("visible_names")
        return result.reply, tools_used, tool_chain, visible_names, result.thinking
