from __future__ import annotations

from typing import TYPE_CHECKING

from agent.core.passive_support import predict_current_user_source_ref
from agent.core.types import ContextRequest
from agent.tools.turn_origin import set_tool_origin
from agent.core.turn_events import TurnEvents
from agent.lifecycle.types import (
    BeforeReasoningCtx,
    BeforeReasoningInput,
    BeforeTurnCtx,
)
from shiori_sdk.channels.message_source import MessageSource
from shiori_sdk.core.conversation import ReasoningStarting
from shiori_sdk.kernel import Veto

if TYPE_CHECKING:
    from agent.context import ContextBuilder
    from agent.tools.registry import ToolRegistry
    from session.manager import SessionManager


class BeforeReasoningPhase:
    """Readies the reasoning: tool context, ``ReasoningStarting``, prompt warmup.

    The steps run in this fixed order; a vetoed ``ReasoningStarting`` skips the
    warmup.
    """

    def __init__(
        self,
        events: TurnEvents,
        tools: ToolRegistry,
        session_manager: SessionManager,
        context: ContextBuilder,
    ) -> None:
        self._events = events
        self._tools = tools
        self._session_manager = session_manager
        self._context = context

    async def run(self, input: BeforeReasoningInput) -> BeforeReasoningCtx:
        """Readies the reasoning and returns its context, aborting or not."""
        self._sync_tool_context(input)
        ctx = _before_reasoning_ctx(input.before_turn)
        await self._emit(ctx)
        if not ctx.abort:
            self._warm_up_prompt(input, ctx)
        return ctx

    def _sync_tool_context(self, input: BeforeReasoningInput) -> None:
        state = input.state
        before_turn = input.before_turn
        if state.session is None:
            raise RuntimeError("BeforeReasoning requires TurnState.session")
        role_id = str(state.session.metadata.get("role_id") or "").strip()
        message_metadata = (
            state.msg.metadata if isinstance(state.msg.metadata, dict) else {}
        )
        source = MessageSource.from_inbound(state.msg)
        set_tool_origin(state.msg)
        self._tools.set_context(
            channel=before_turn.channel,
            chat_id=before_turn.chat_id,
            session_key=before_turn.session_key,
            # 模型可以用 session_key 参数改写检索范围，回合自身的会话另存一份。
            turn_session_key=before_turn.session_key,
            role_id=role_id,
            current_user_message=before_turn.content,
            role_config_version=str(message_metadata.get("role_config_version") or ""),
            thread_id=str(
                message_metadata.get("thread_id")
                or state.session.metadata.get("thread_id")
                or ""
            ),
            delivery_key=str(message_metadata.get("delivery_key") or ""),
            # 回合的发送者、是否出自用户本人（规则见 ``TurnState.is_user_authored``）
            # 与所在上下文（user / external；非角色共享会话为空），供工具按回合
            # 身份收窄行为（#540）。
            sender_id=source.sender_id or "",
            sender_is_user="true" if state.is_user_authored() else "false",
            account_full_tools=(
                "true"
                if self._tools.allows_full_tools(state.msg, role_id=role_id)
                else "false"
            ),
            context_scope=state.context_scope or "",
            current_timestamp=before_turn.timestamp.isoformat(),
            current_user_source_ref=predict_current_user_source_ref(
                session_manager=self._session_manager,
                session=state.session,
            ),
            defer_push_session_sync="true",
        )

    async def _emit(self, ctx: BeforeReasoningCtx) -> None:
        """Emits ``ReasoningStarting`` and writes the final event back to ``ctx``."""

        def apply(event: ReasoningStarting) -> None:
            ctx.skill_names[:] = event.skill_names
            ctx.retrieved_memory_block = event.retrieved_memory_block
            ctx.extra_hints[:] = event.extra_hints

        def vetoed(veto: Veto) -> None:
            ctx.abort, ctx.abort_reply = True, veto.reason

        await self._events.emit(_reasoning_starting(ctx), apply, vetoed)

    def _warm_up_prompt(
        self, input: BeforeReasoningInput, ctx: BeforeReasoningCtx
    ) -> None:
        state = input.state
        _ = self._context.render(
            ContextRequest(
                history=[],
                current_message="",
                skill_names=ctx.skill_names,
                channel=ctx.channel,
                chat_id=ctx.chat_id,
                message_timestamp=ctx.timestamp,
                retrieved_memory_block=ctx.retrieved_memory_block,
                context_scope=state.context_scope,
                # 与正式渲染同一来源：外部回合据此注入当前会话的群笔记。
                thread_id=state.thread_id,
            ),
            session_metadata=(
                dict(state.session.metadata)
                if state.session is not None
                and isinstance(state.session.metadata, dict)
                else None
            ),
        )


def _before_reasoning_ctx(before_turn: BeforeTurnCtx) -> BeforeReasoningCtx:
    """The reasoning's context, carried over from the turn's."""
    return BeforeReasoningCtx(
        session_key=before_turn.session_key,
        channel=before_turn.channel,
        chat_id=before_turn.chat_id,
        content=before_turn.content,
        timestamp=before_turn.timestamp,
        skill_names=list(before_turn.skill_names),
        retrieved_memory_block=before_turn.retrieved_memory_block,
        extra_hints=list(before_turn.extra_hints),
    )


def _reasoning_starting(ctx: BeforeReasoningCtx) -> ReasoningStarting:
    """The ``ReasoningStarting`` projection of the reasoning's context."""
    return ReasoningStarting(
        session_key=ctx.session_key,
        channel=ctx.channel,
        chat_id=ctx.chat_id,
        content=ctx.content,
        timestamp=ctx.timestamp,
        skill_names=tuple(ctx.skill_names),
        retrieved_memory_block=ctx.retrieved_memory_block,
        extra_hints=tuple(ctx.extra_hints),
    )
