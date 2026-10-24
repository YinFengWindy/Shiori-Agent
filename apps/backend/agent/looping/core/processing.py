"""AgentLoop 主循环与消息处理。"""

from __future__ import annotations

from agent.tools.turn_scope import tool_turn
from agent.background.result_history import commit_background_fact
from agent.turns.channel_sequence_commit import ChannelSequenceDeliveryError
from agent.turns.channel_sequence import (
    without_channel_sequence,
    channel_sequence_context,
)
from agent.turns.reply_interruption import (
    current_reply_interruption,
    reply_interruption_scope,
    ReplyInterruption,
)

import asyncio
import time
from datetime import datetime

from core.error_context import current_session_key
from ..interrupt import (
    TurnInterruptState,
    run_turn_task,
    turn_tracking_key,
    current_tracking_key,
)
from collections.abc import Callable
from contextlib import nullcontext
from functools import partial
from shiori_sdk.accounts.models import AccountNotFoundError
from dataclasses import replace

from core.roles.role_runtime import RoleBusyError, RoleExecutionContext
from core.roles.services import RoleSessionService
from shiori_sdk.external_turns import ExternalTurnResult
from bus.events import InboundItem, SpawnCompletionItem
from shiori_sdk.messages import InboundMessage, OutboundMessage
from bus.processing import ProcessingState

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from shiori_sdk.kernel import Kernel

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

            await self.process_inbound(item)

    async def process_inbound(self, item: InboundItem) -> None:
        """Processes queued input or a typed internal completion on this runtime."""
        key = item.session_key
        if await self._compact_command(item, key, dispatch_outbound=True) is not None:
            return
        # Typed internal completions keep their own session identity. Their
        # channel/chat is a return destination, not an admitted external origin.
        tracking_key = key
        if isinstance(item, SpawnCompletionItem) and item.origin is not None:
            tracking_key = f"{key}\x1fbackground\x1f{item.event.job_id}"
        if isinstance(item, InboundMessage):
            metadata = item.metadata
            tracking_key = turn_tracking_key(
                key,
                item.channel,
                item.chat_id,
                account_id=str(metadata.get("account_id") or ""),
                chat_type=str(metadata.get("chat_type") or ""),
                message_thread_id=str(metadata.get("message_thread_id") or ""),
            )
        authority = None
        if isinstance(item, SpawnCompletionItem) and item.origin is not None:
            try:
                authority = self._background_outbound_authority(item.origin)
            except (PermissionError, AccountNotFoundError):
                # A revoked internal return destination must not receive an error.
                logger.info("Spawn result destination no longer authorized for %s", key)
                return
        with (
            self.bus.outbound_authority(authority)
            if authority is not None
            else nullcontext()
        ):
            self._active_turn_states[tracking_key] = self._build_initial_turn_state(
                item, key
            )
            task = asyncio.create_task(
                run_turn_task(
                    lambda: self._process_role_scoped(item, key),
                    detached=False,
                    tracking_key=tracking_key,
                )
            )
            self._active_tasks[tracking_key] = task
            try:
                await task
            except asyncio.CancelledError:
                if asyncio.current_task().cancelling():
                    raise
                logger.info(f"Turn cancelled for {key}")
            except ChannelSequenceDeliveryError:
                logger.exception("Reply sequence stopped for %s", key)
            except Exception as e:
                logger.error(f"处理消息出错: {e}", exc_info=True)
                await self.bus.publish_outbound(
                    OutboundMessage(
                        channel=item.channel,
                        chat_id=item.chat_id,
                        content=f"出错：{e}",
                        metadata=dict(getattr(item, "metadata", {}) or {}),
                    )
                )
            finally:
                if self._active_tasks.get(tracking_key) is task:
                    self._active_tasks.pop(tracking_key, None)
                    self._active_turn_states.pop(tracking_key, None)

    def _background_outbound_authority(
        self, origin: InboundMessage
    ) -> Callable[[], bool] | None:
        """Capture the same account connection fence for both internal report entries."""
        registry = getattr(self, "_role_runtime_registry", None)
        account_id = str(origin.metadata.get("account_id") or "")
        if registry is None or not account_id:
            return None
        accounts = registry.repository.store.accounts
        access = accounts.authorize(
            account_id, str(origin.metadata.get("role_id") or "")
        )
        return partial(accounts.validate_access, access)

    @property
    def processing_state(self) -> ProcessingState | None:
        return self._processing_state

    @property
    def role_runtime_registry(self):
        """Returns the registry used by direct turns and role-owned background work."""

        return self._role_runtime_registry

    @property
    def active_turn_states(self) -> dict[str, TurnInterruptState]:
        return self._active_turn_states

    def stop(self) -> None:
        self._running = False
        logger.info("AgentLoop 停止")

    def bind_kernel(self, kernel: Callable[[], "Kernel"]) -> None:
        """让被动回合的回合、步骤与工具事件每次发出时经 ``kernel()`` 返回的内核。

        ``kernel`` 通常读本代插件内核：其中插件被卸载或新加载后，下一次
        回合/工具调用即按当前 ACTIVE 插件执行。
        """
        self._reasoner.bind_kernel(kernel)
        self._agent_core.bind_kernel(kernel)

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
            registry = getattr(self, "_role_runtime_registry", None)
            metadata = getattr(msg, "metadata", None)
            metadata = metadata if isinstance(metadata, dict) else {}
            role_id = str(metadata.get("role_id") or "").strip()
            if not role_id and key.startswith("role:"):
                role_id = key.removeprefix("role:").strip()
            if registry is not None and role_id:
                purpose = "vision" if getattr(msg, "media", None) else "chat"
                runtime = await registry.get(role_id)
                with runtime.activate_model(purpose):
                    outbound = await self._core_runner.process(
                        msg,
                        key,
                        dispatch_outbound=dispatch_outbound,
                    )
            else:
                outbound = await self._core_runner.process(
                    msg,
                    key,
                    dispatch_outbound=dispatch_outbound,
                )
            if resumed_from_interrupt:
                self._interrupt_states.pop(current_tracking_key(key), None)
            return outbound
        except asyncio.CancelledError:
            await self._observe_turn_cancelled(msg, key)
            raise
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
        """Dispatches role-bound messages through their owning role runtime before a turn."""

        registry = getattr(self, "_role_runtime_registry", None)
        metadata = getattr(item, "metadata", None)
        if (
            registry is not None
            and isinstance(item, SpawnCompletionItem)
            and item.origin is not None
        ):
            origin = item.origin
            role_id = str(origin.metadata["role_id"])
            # Internal completion owns a captured destination, never a newly
            # admitted external message or an inherited generation's context.
            context = registry.create_context(
                role_id=role_id,
                thread_id=str(origin.metadata["thread_id"]),
                transport_channel=origin.channel,
                transport_chat_id=origin.chat_id,
                source="background_result",
                work_kind="passive_turn",
                request_id=f"spawn:{item.event.job_id}",
            )
            metadata = {**origin.metadata, **context.to_metadata()}
            item = replace(item, origin=replace(origin, metadata=metadata))
        if registry is None or not isinstance(metadata, dict):
            return await self._process(
                item,
                session_key=session_key,
                dispatch_outbound=dispatch_outbound,
            )
        context = registry.context_from_metadata(metadata)
        if context is None:
            if str(metadata.get("role_id") or "").strip() or session_key.startswith(
                "role:"
            ):
                raise ValueError("角色回合缺少完整 RoleExecutionContext")
            return await self._process(
                item,
                session_key=session_key,
                dispatch_outbound=dispatch_outbound,
            )

        interruption = current_reply_interruption()
        if interruption is not None:
            interruption.role_lookup = lambda: registry.repository.store.get_role(
                context.role_id
            )

        async def operation() -> OutboundMessage:
            if isinstance(item, SpawnCompletionItem) and item.origin is not None:
                if not self.bus.outbound_authorized():
                    raise asyncio.CancelledError
                role = registry.repository.store.get_role(context.role_id)
                if role is None:
                    raise asyncio.CancelledError
                RoleSessionService(self.session_manager).open_by_role(role)
            return await self._process(
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
            sender=str(merged_metadata.get("sender_id") or "user"),
            chat_id=chat_id,
            content=content,
            media=list(media or []),
            metadata=merged_metadata,
        )
        key = session_key
        command = await self._compact_command(msg, key, dispatch_outbound=False)
        if command is not None:
            return command.content
        self._active_turn_states[key] = self._build_initial_turn_state(msg, key)
        with (
            without_channel_sequence(),
            reply_interruption_scope(
                current_reply_interruption()
                if channel == "desktop" and merged_metadata.get("turn_id")
                else None
            ),
        ):
            task = asyncio.create_task(
                run_turn_task(
                    lambda: self._process_role_scoped(
                        msg,
                        session_key=key,
                        dispatch_outbound=False,
                    ),
                    detached=False,
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

    async def process_external_turn(
        self,
        context: RoleExecutionContext,
        admit: Callable[[], InboundMessage | None],
    ) -> ExternalTurnResult:
        """Runs a plugin-submitted external turn now, unless the role is busy.

        ``context`` names the role and the turn's source thread
        (``RoleTurnRouter.network_turn_context``). The turn never waits for the
        role's turn gate: while any other role work holds or awaits it,
        ``busy`` returns and ``admit`` is never called, so nothing is routed
        or stored. Holding the gate, ``admit`` routes the message
        (``RoleTurnRouter.route``); None from it (a duplicate) returns
        ``duplicate``. The turn bypasses the channel inbound queue, never
        dispatches outbound and publishes no stream deltas.

        The turn is not the role session's interruptible turn: desktop or
        channel interrupts never reach it, and it neither reports progress
        into nor resumes their interrupt state. Cancelling the caller cancels
        the turn. Once it holds the gate, later role work waits for it.
        """
        registry = self._role_runtime_registry
        if registry is None:
            raise RuntimeError("RoleRuntimeRegistry 未配置")
        if context.work_kind != "passive_turn":
            raise ValueError("外部回合必须是 passive_turn")
        started = False

        async def operation() -> ExternalTurnResult:
            nonlocal started
            started = True
            routed = admit()
            if routed is None:
                return ExternalTurnResult("duplicate")
            msg = replace(
                routed,
                metadata={**routed.metadata, "suppress_stream_events": True},
            )
            outbound = await self._process(
                msg, session_key=msg.session_key, dispatch_outbound=False
            )
            return ExternalTurnResult("replied", outbound.content)

        async def detached_turn() -> ExternalTurnResult:
            try:
                return await registry.dispatch_passive_turn(
                    context, operation, reject_busy=True
                )
            except RoleBusyError:
                # Only the gate's refusal means busy; a failure inside the
                # turn propagates.
                if started:
                    raise
                return ExternalTurnResult("busy")

        # Its own task keeps the detached flag and the turn's context variables
        # inside; awaiting it directly forwards the caller's cancellation.
        return await asyncio.create_task(
            run_turn_task(detached_turn, detached=True),
            name=f"agent_loop_external:{context.role_id}",
        )

    async def process_background_result(
        self,
        context: RoleExecutionContext,
        admit: Callable[[], InboundMessage],
    ) -> None:
        """Report on the original thread, under its role gate, without user intake."""
        registry = self._role_runtime_registry
        if registry is None:
            raise RuntimeError("RoleRuntimeRegistry 未配置")

        origin = admit()
        authority = self._background_outbound_authority(origin)
        transport = channel_sequence_context()
        role = registry.repository.store.get_role(context.role_id)
        if role is None:
            raise asyncio.CancelledError
        interruption = (
            ReplyInterruption(
                role_lookup=lambda: registry.repository.store.get_role(context.role_id)
            )
            if transport is not None
            and role.runtime_config.get("natural_chat_enabled") is True
            else None
        )
        predecessors = (
            transport.owner.background_tasks(origin) if transport is not None else ()
        )

        async def operation() -> None:
            # Recheck both report admission and the captured connection after the gate.
            if authority is not None and not authority():
                raise asyncio.CancelledError
            message = admit()
            result_text = str(message.metadata.pop("background_result_text"))
            role = registry.repository.store.get_role(context.role_id)
            if role is None:
                raise asyncio.CancelledError
            RoleSessionService(self.session_manager).open_by_role(role)
            if interruption is not None:
                await commit_background_fact(
                    self.session_manager,
                    message.session_key,
                    metadata=message.metadata,
                    call_id=context.request_id,
                    name="background_result",
                    arguments={},
                    result=result_text,
                )
            await self._process(
                message, session_key=message.session_key, dispatch_outbound=True
            )

        async def detached_turn() -> None:
            if predecessors:
                await asyncio.shield(
                    asyncio.gather(*predecessors, return_exceptions=True)
                )
            with (
                reply_interruption_scope(interruption),
                (
                    self.bus.outbound_authority(authority)
                    if authority is not None
                    else nullcontext()
                ),
            ):
                await registry.dispatch_passive_turn(context, operation)

        task = asyncio.create_task(
            run_turn_task(detached_turn, detached=True),
            name=f"agent_loop_background_result:{context.role_id}",
        )
        registration = (
            transport.owner.register_background(
                origin,
                interruption,
                task,
                senders=(
                    frozenset({origin.sender})
                    if origin.metadata.get("chat_type") in {"group", "supergroup"}
                    else None
                ),
            )
            if transport is not None and interruption is not None
            else None
        )
        try:
            await task
        except asyncio.CancelledError:
            if asyncio.current_task().cancelling():
                raise
        finally:
            if transport is not None and registration is not None:
                transport.owner.forget_background(registration)

    def _ensure_direct_role_context(
        self,
        metadata: dict[str, object],
        *,
        session_key: str,
        channel: str,
        chat_id: str,
    ) -> None:
        """Adds a role context to direct entrypoints backed by a formal role session."""

        registry = getattr(self, "_role_runtime_registry", None)
        if registry is None or registry.context_from_metadata(metadata) is not None:
            return
        session = self.session_manager.get_or_create(session_key)
        session_metadata = (
            session.metadata if isinstance(session.metadata, dict) else {}
        )
        role_id = str(
            metadata.get("role_id") or session_metadata.get("role_id") or ""
        ).strip()
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
        """Runs non-turn role work through the role runtime's thread execution boundary."""

        registry = self._role_runtime_registry
        if registry is None:
            raise RuntimeError("RoleRuntimeRegistry 未配置")
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

    @tool_turn
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
            build_context_frame_content,
            build_context_frame_message,
        )
        from shiori_sdk.prompting import PromptSectionRender

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
