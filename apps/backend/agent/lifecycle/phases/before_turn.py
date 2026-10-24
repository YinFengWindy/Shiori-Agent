from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Protocol, cast

from shiori_sdk.commands import CommandInput
from agent.lifecycle.commands import abort_command
from conversation.commands import generation_commands
from agent.core.turn_events import TurnEvents, freeze_top_level, read_only
from session.manager.models import consolidation_cursor
from agent.core.runtime_support import SessionLike
from agent.core.types import ContextBundle
from agent.lifecycle.types import BeforeTurnCtx, TurnState
from conversation.context_scope import (
    session_context_view,
)
from shiori_sdk.core.conversation import ConversationMessage, TurnStarting
from shiori_sdk.kernel import Veto

if TYPE_CHECKING:
    from agent.core.passive_turn import ContextStore
    from conversation.context_scope import ContextView
    from session.manager import SessionManager

logger = logging.getLogger(__name__)


class MemoryConsolidator(Protocol):
    """Schedule semantic memory independently of model-window compaction."""

    def request_memory_consolidation(self, session_key: str) -> None: ...

    def get_memory_consolidation_failure(self, session_key: str) -> str | None: ...


class MemoryConsolidationFailedError(RuntimeError):
    """Raised when background memory consolidation has definitively failed."""


class BeforeTurnPhase:
    """Prepares a turn: session, command answer, backlog guard, context, ``TurnStarting``.

    The steps run in this fixed order. A registered command or the memory
    backlog guard ends the turn with an aborting context before retrieval; that
    context still goes out as ``TurnStarting``.
    """

    def __init__(
        self,
        events: TurnEvents,
        session_manager: SessionManager,
        context_store: ContextStore,
        *,
        keep_count: int = 20,
        consolidator: MemoryConsolidator | None = None,
    ) -> None:
        self._events = events
        self._session_manager = session_manager
        self._context_store = context_store
        self._keep_count = max(1, int(keep_count))
        self._min_new = max(5, self._keep_count // 2)
        self._threshold = self._keep_count + self._min_new
        self._consolidator = consolidator

    async def run(self, state: TurnState) -> BeforeTurnCtx:
        """Prepares the turn and returns its context, aborting or not."""
        session = self._acquire_session(state)
        ctx = await self._answer_command(state, session)
        if ctx is None:
            ctx = self._guard_memory_backlog(state, session)
        if ctx is None:
            bundle = await self._context_store.prepare(
                msg=state.msg,
                session_key=state.session_key,
                session=session,
                context_view=state.context_view,
            )
            ctx = _before_turn_ctx(state, bundle)
        await self._emit(ctx)
        return ctx

    def _acquire_session(self, state: TurnState) -> SessionLike:
        session = self._session_manager.get_or_create(state.session_key)
        message_role_id = str((state.msg.metadata or {}).get("role_id") or "").strip()
        session_metadata = getattr(session, "metadata", None)
        if not isinstance(session_metadata, dict):
            session_metadata = {}
            session.metadata = session_metadata
        session_role_id = str(session_metadata.get("role_id") or "").strip()
        if message_role_id and session_role_id and message_role_id != session_role_id:
            raise ValueError(
                "session role scope mismatch: "
                f"session={session_role_id!r} message={message_role_id!r}"
            )
        if message_role_id and not session_role_id:
            session_metadata["role_id"] = message_role_id
            save = getattr(self._session_manager, "save", None)
            if callable(save):
                save(session)
        state.session = session
        # 角色共享会话混存各渠道的消息，回合只看与所在会话同类上下文的历史；
        # 归属按此刻的身份绑定计算。其他会话只有一段对话，不需要划分。
        if message_role_id or session_role_id:
            state.context_view = session_context_view(
                self._session_manager.workspace,
                session_key=state.session_key,
                role_id=message_role_id or session_role_id,
                thread_id=state.thread_id,
            )
        return cast(SessionLike, session)

    async def _answer_command(
        self, state: TurnState, session: SessionLike
    ) -> BeforeTurnCtx | None:
        """Answers a registered bot command right after the session is acquired.

        It runs before the memory backlog guard and retrieval, so a command still
        answers when the backlog refuses ordinary turns. The registry is read from
        the current kernel on every turn: a plugin unloaded since then no longer
        answers.
        """
        commands = generation_commands(self._events.kernel)
        handler = None if commands is None else commands.handler(state.msg.content)
        if handler is None:
            return None
        reply = await handler(
            CommandInput(
                content=state.msg.content,
                session_key=state.session_key,
                messages=tuple(session.messages),
                last_consolidated=session.last_consolidated,
            )
        )
        logger.info("command answered: session=%s", state.session_key)
        return abort_command(state, reply)

    def _guard_memory_backlog(
        self, state: TurnState, session: SessionLike
    ) -> BeforeTurnCtx | None:
        """An aborting context when the unconsolidated backlog is over the threshold.

        With a consolidator the turn continues on the hot window while
        consolidation runs, unless consolidation has already failed.
        """
        if bool((state.msg.metadata or {}).get("skip_memory_context_guard")):
            return None
        messages = list(getattr(session, "messages", []))
        # 记忆积压按本回合所属类别的记忆游标计算，与模型窗口水位独立。
        last = _clamp_context_cursor(
            consolidation_cursor(
                session, state.context_view.scope if state.context_view else None
            ),
            len(messages),
        )
        pending = _pending_messages(messages, last, state.context_view)
        if pending < self._threshold:
            return None

        if self._consolidator is not None:
            failure = self._consolidator.get_memory_consolidation_failure(
                state.session_key
            )
            if failure is not None:
                raise MemoryConsolidationFailedError(
                    f"记忆整理失败，请检查模型或网络配置后重试。详情：{failure}"
                )
            self._consolidator.request_memory_consolidation(state.session_key)
            logger.info(
                "memory context guard continued with hot window while consolidation runs: session=%s pending=%d threshold=%d",
                state.session_key,
                pending,
                self._threshold,
            )
            return None

        logger.error(
            "memory context guard blocked turn: session=%s pending=%d threshold=%d last_consolidated=%d total=%d",
            state.session_key,
            pending,
            self._threshold,
            last,
            len(messages),
        )
        return BeforeTurnCtx(
            session_key=state.session_key,
            channel=state.msg.context_channel,
            chat_id=state.msg.context_chat_id,
            content=state.msg.content,
            timestamp=state.msg.timestamp,
            retrieved_memory_block="",
            retrieval_trace_raw=None,
            history_messages=(),
            context_scope=state.context_scope,
            abort=True,
            abort_reply=_memory_context_guard_reply(
                pending=pending,
                threshold=self._threshold,
                keep_count=self._keep_count,
                last_consolidated=last,
                total_messages=len(messages),
            ),
            extra_metadata={
                "memory_context_guard": {
                    "pending": pending,
                    "threshold": self._threshold,
                    "keep_count": self._keep_count,
                    "last_consolidated": last,
                    "total_messages": len(messages),
                }
            },
        )

    async def _emit(self, ctx: BeforeTurnCtx) -> None:
        """Emits ``TurnStarting`` and writes the final event back to ``ctx``."""

        def apply(event: TurnStarting) -> None:
            ctx.skill_names[:] = event.skill_names
            ctx.extra_hints[:] = event.extra_hints
            ctx.extra_metadata = dict(event.extra_metadata)

        def vetoed(veto: Veto) -> None:
            ctx.abort, ctx.abort_reply = True, veto.reason

        await self._events.emit(_turn_starting(ctx), apply, vetoed)


def _before_turn_ctx(state: TurnState, bundle: ContextBundle) -> BeforeTurnCtx:
    """The context of a turn that goes on to reasoning."""
    return BeforeTurnCtx(
        session_key=state.session_key,
        channel=state.msg.context_channel,
        chat_id=state.msg.context_chat_id,
        content=state.msg.content,
        timestamp=state.msg.timestamp,
        skill_names=list(bundle.skill_mentions),
        retrieved_memory_block=bundle.retrieved_memory_block,
        retrieval_trace_raw=bundle.retrieval_trace_raw,
        history_messages=tuple(bundle.history_messages),
        context_scope=state.context_scope,
    )


def _turn_starting(ctx: BeforeTurnCtx) -> TurnStarting:
    """The ``TurnStarting`` projection of the turn's context."""
    return TurnStarting(
        session_key=ctx.session_key,
        channel=ctx.channel,
        chat_id=ctx.chat_id,
        content=ctx.content,
        timestamp=ctx.timestamp,
        context_scope=ctx.context_scope,
        history=tuple(
            ConversationMessage(
                role=message.role,
                content=message.content,
                tools_used=tuple(message.tools_used),
            )
            for message in ctx.history_messages
        ),
        retrieved_memory_block=ctx.retrieved_memory_block,
        retrieval_trace=freeze_top_level(ctx.retrieval_trace_raw),
        skill_names=tuple(ctx.skill_names),
        extra_hints=tuple(ctx.extra_hints),
        extra_metadata=read_only(ctx.extra_metadata),
    )


def _clamp_context_cursor(cursor: int, total_messages: int) -> int:
    """把本回合所在上下文的整理游标夹到 ``[0, total_messages]``。

    游标由 ``consolidation_cursor`` 给出，已经是 int（会话字段按 int 存取，数字字符串在
    ``consolidation_cursor`` 里就转成 int，非数字直接报错），这里只需夹范围。
    """
    return min(max(0, cursor), max(0, int(total_messages)))


def _pending_messages(
    messages: list[dict], last_consolidated: int, context_view: ContextView | None
) -> int:
    """本回合所在整类上下文在整理游标之后尚未整理的消息数；非角色会话数整段。

    整理按整类上下文进行、共用一个游标，所以按 ``category`` 数：外部回合也把
    其他群与陌生私聊的积压算进来，不只数本会话。
    """
    tail = messages[last_consolidated:]
    if context_view is None:
        return len(tail)
    category = context_view.category
    return sum(1 for message in tail if category.includes(message))


def _memory_context_guard_reply(
    *,
    pending: int,
    threshold: int,
    keep_count: int,
    last_consolidated: int,
    total_messages: int,
) -> str:
    return (
        "记忆归档现在处于异常积压状态，我先暂停本轮普通回复，避免把未归档历史继续塞进模型上下文。\n"
        f"当前未归档消息数 {pending}，安全阈值 {threshold}，热上下文保留 {keep_count}，"
        f"last_consolidated={last_consolidated}，total_messages={total_messages}。\n"
        "请先修复 memory consolidation 后再重试。"
    )
