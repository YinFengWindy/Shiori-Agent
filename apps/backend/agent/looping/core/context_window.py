"""Host context-window control plane; channel commands keep normal admission."""

from bus.events import InboundMessage, OutboundMessage
from bus.events_context import ContextWindowChanged
from conversation.context_scope import session_context_view
from core.roles.model_errors import ModelConfigurationError
from shiori_sdk.commands import normalize_command
from agent.core.passive_turn.reasoner import DefaultReasoner
from session.maintenance_progress import window_key
from core.common.error_summary import public_validation_message


def context_unavailable(session_key: str, reason: str, *, busy: bool = False) -> dict:
    """Unknown usage must remain null rather than a fabricated empty context."""
    return {
        "session_key": session_key,
        "context_key": "",
        "model": "",
        "model_identity": "",
        "tokens": None,
        "source": None,
        "model_context_window": None,
        "input_limit_tokens": None,
        "can_compact": False,
        "busy": busy,
        "reason": reason,
        "result": None,
    }


def format_compaction_status(state: dict) -> str:
    """The command and desktop expose the same staged controller result."""
    result = state.get("result")
    if not result:
        return str(state.get("reason") or "没有可压缩的完整轮次")
    if not result["committed"]:
        prefix = "记忆已整理、压缩失败" if result["memory_committed"] else "压缩失败"
        return f"{prefix}：{result['error']}"
    return (
        f"上下文已压缩：{result['before_tokens']} → {result['after_tokens']} token（估算）；"
        f"保留 {result['retained_turns']} 个完整轮次，原文从位置 {result['retained_start']} 保留。"
    )


class _ContextWindowMixin:
    async def inspect_context_window(
        self, msg: InboundMessage, session_key: str, *, compact: bool = False
    ) -> dict:
        """Run a read/manual operation under the actual role's shared execution gate."""
        self._ensure_direct_role_context(
            msg.metadata,
            session_key=session_key,
            channel=msg.channel,
            chat_id=msg.chat_id,
        )
        reasoner = self._reasoner
        if not isinstance(reasoner, DefaultReasoner) or reasoner.context_window is None:
            return context_unavailable(session_key, "上下文压缩尚未就绪")
        registry = self._role_runtime_registry
        context = registry.context_from_metadata(msg.metadata) if registry else None
        if session_key.startswith("role:") and context is None:
            raise ValueError("上下文操作缺少完整 RoleExecutionContext")
        if context and session_key != self.session_manager.role_session_key(
            context.role_id
        ):
            raise ValueError("上下文操作的角色与会话不匹配")
        runtime = await registry.get(context.role_id) if registry and context else None
        if (
            (runtime and runtime.busy)
            or (self._processing_state and self._processing_state.is_busy(session_key))
            or reasoner.context_window.controller.memory.is_busy(session_key)
            or reasoner.context_window.controller.is_busy(session_key)
        ):
            return context_unavailable(
                session_key, "正在回复或整理上下文，请稍后重试", busy=True
            )
        session = self.session_manager.get_or_create(session_key)
        view = session_context_view(
            self.session_manager.workspace,
            session_key=session_key,
            role_id=context.role_id if context else "",
            thread_id=context.thread_id if context else "",
        )

        async def inspect():
            return await reasoner.context_window.inspect(
                session=session, context_view=view, msg=msg, compact=compact
            )

        async def with_model():
            if compact:
                await self._event_bus.observe(
                    ContextWindowChanged(session_key, window_key(view), busy=True)
                )
            if runtime is None:
                return await inspect()
            with runtime.activate_model("chat"):
                return await inspect()

        try:
            if compact and runtime and context:
                return await runtime.execute_thread(
                    context, with_model, reject_busy=True
                )
            return await with_model()
        except ModelConfigurationError as error:
            return context_unavailable(session_key, str(error))
        finally:
            if compact:
                await self._event_bus.observe(
                    ContextWindowChanged(session_key, window_key(view))
                )

    async def _compact_command(
        self, item, session_key: str, *, dispatch_outbound: bool
    ) -> OutboundMessage | None:
        if (
            not isinstance(item, InboundMessage)
            or normalize_command(item.content) != "/compact"
        ):
            return None
        try:
            state = await self.inspect_context_window(item, session_key, compact=True)
            content = format_compaction_status(state)
        except Exception as error:
            # The transport boundary reports failure; it never sends a fallback
            # model request, persists a chat message, or advances the mood owner.
            content = "压缩失败：" + public_validation_message(
                error, fallback="上下文操作未完成，请稍后重试"
            )
        response = OutboundMessage(
            channel=item.channel,
            chat_id=item.chat_id,
            content=content,
            metadata=dict(item.metadata or {}),
        )
        if dispatch_outbound:
            await self.bus.publish_outbound(response)
        return response
