from __future__ import annotations

from dataclasses import dataclass
import logging
from typing import TYPE_CHECKING, Protocol, TypeAlias, cast

from shiori_sdk.commands import CommandInput
from agent.lifecycle.commands import abort_command
from bus.event_bus import EventBus
from session.manager.models import consolidation_cursor
from agent.core.runtime_support import SessionLike
from agent.core.types import ContextBundle
from agent.lifecycle.phase import (
    PhaseFrame,
    PhaseModule,
    append_string_exports,
    collect_prefixed_slots,
    topo_sort_modules,
)
from agent.lifecycle.types import BeforeTurnCtx, TurnState
from conversation.context_scope import (
    session_context_view,
)

if TYPE_CHECKING:
    from agent.core.passive_turn import ContextStore
    from conversation.context_scope import ContextView
    from session.manager import SessionManager

logger = logging.getLogger(__name__)


@dataclass
class BeforeTurnFrame(PhaseFrame[TurnState, BeforeTurnCtx]):
    """Host frame exposing a bounded command view to lifecycle contributors."""

    @property
    def command(self) -> CommandInput:
        """Read memory progress without exposing session persistence internals."""
        session = self.input.session
        return CommandInput(
            content=self.input.msg.content,
            session_key=self.input.session_key,
            messages=tuple(session.messages) if session is not None else (),
            last_consolidated=session.last_consolidated if session is not None else 0,
            has_session=session is not None,
        )

    def abort_command(self, reply: str) -> None:
        """Create the ordinary host abort context before any retrieval or LLM call."""
        self.slots["session:ctx"] = abort_command(self.input, reply)


BeforeTurnModules: TypeAlias = list[PhaseModule[BeforeTurnFrame]]


class MemoryConsolidator(Protocol):
    """Schedule memory and delegate independent model-window maintenance."""

    def request_memory_consolidation(self, session_key: str) -> None: ...

    def get_memory_consolidation_failure(self, session_key: str) -> str | None: ...

    async def ensure_context_window(
        self,
        session_key: str,
        current_content: str = "",
        view: ContextView | None = None,
        *,
        input_token_threshold: int,
    ) -> bool: ...


class MemoryConsolidationFailedError(RuntimeError):
    """Raised when background memory consolidation has definitively failed."""


_SESSION_SLOT = "session:session"
_CONTEXT_BUNDLE_SLOT = "session:context_bundle"
_CTX_SLOT = "session:ctx"
_EXTRA_HINT_PREFIX = "session:extra_hint:"
_ABORT_REPLY_SLOT = "session:abort_reply"


class _AcquireSessionModule:
    slot = "before_turn.acquire_session"
    requires: tuple[str, ...] = ()
    produces = (_SESSION_SLOT,)

    def __init__(self, session_manager: SessionManager) -> None:
        self._session_manager = session_manager

    async def run(self, frame: BeforeTurnFrame) -> BeforeTurnFrame:
        state = frame.input
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
        frame.slots[_SESSION_SLOT] = session
        return frame


class _PrepareContextModule:
    slot = "before_turn.prepare_context"
    requires = ("before_turn.acquire_session", _SESSION_SLOT)
    produces = (_CONTEXT_BUNDLE_SLOT,)

    def __init__(self, context_store: ContextStore) -> None:
        self._context_store = context_store

    async def run(self, frame: BeforeTurnFrame) -> BeforeTurnFrame:
        if _CTX_SLOT in frame.slots:
            return frame
        state = frame.input
        session = cast(SessionLike, frame.slots[_SESSION_SLOT])
        bundle = await self._context_store.prepare(
            msg=state.msg,
            session_key=state.session_key,
            session=session,
            context_view=state.context_view,
        )
        frame.slots[_CONTEXT_BUNDLE_SLOT] = bundle
        return frame


class _MemoryContextGuardModule:
    slot = "before_turn.memory_context_guard"
    requires = ("before_turn.acquire_session", _SESSION_SLOT)
    produces = (_CTX_SLOT,)

    def __init__(
        self,
        session_manager: SessionManager,
        keep_count: int,
        consolidator: MemoryConsolidator | None = None,
    ) -> None:
        self._session_manager = session_manager
        self._keep_count = max(1, int(keep_count))
        self._min_new = max(5, self._keep_count // 2)
        self._threshold = self._keep_count + self._min_new
        self._consolidator = consolidator

    async def run(self, frame: BeforeTurnFrame) -> BeforeTurnFrame:
        if _CTX_SLOT in frame.slots:
            return frame
        state = frame.input
        if bool((state.msg.metadata or {}).get("skip_memory_context_guard")):
            return frame
        session = cast(SessionLike, frame.slots[_SESSION_SLOT])
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
            return frame

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
            return frame

        logger.error(
            "memory context guard blocked turn: session=%s pending=%d threshold=%d last_consolidated=%d total=%d",
            state.session_key,
            pending,
            self._threshold,
            last,
            len(messages),
        )
        frame.slots[_CTX_SLOT] = BeforeTurnCtx(
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
        return frame


class _BuildBeforeTurnCtxModule:
    slot = "before_turn.build_ctx"
    requires = ("before_turn.prepare_context", _CONTEXT_BUNDLE_SLOT)
    produces = (_CTX_SLOT,)

    async def run(self, frame: BeforeTurnFrame) -> BeforeTurnFrame:
        if _CTX_SLOT in frame.slots:
            return frame
        state = frame.input
        bundle = cast(ContextBundle, frame.slots[_CONTEXT_BUNDLE_SLOT])
        frame.slots[_CTX_SLOT] = BeforeTurnCtx(
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
        return frame


class _EmitBeforeTurnCtxModule:
    slot = "before_turn.emit"
    requires = ("before_turn.build_ctx", _CTX_SLOT)
    produces = (_CTX_SLOT,)

    def __init__(self, bus: EventBus) -> None:
        self._bus = bus

    async def run(self, frame: BeforeTurnFrame) -> BeforeTurnFrame:
        ctx = cast(BeforeTurnCtx, frame.slots[_CTX_SLOT])
        frame.slots[_CTX_SLOT] = await self._bus.emit(ctx)
        return frame


class _ReturnBeforeTurnCtxModule:
    slot = "before_turn.return"
    requires = ("before_turn.collect_exports", _CTX_SLOT)

    async def run(self, frame: BeforeTurnFrame) -> BeforeTurnFrame:
        frame.output = cast(BeforeTurnCtx, frame.slots[_CTX_SLOT])
        return frame


class _CollectBeforeTurnExportSlotsModule:
    slot = "before_turn.collect_exports"
    requires = ("before_turn.emit", _CTX_SLOT)
    produces = (_CTX_SLOT,)

    async def run(self, frame: BeforeTurnFrame) -> BeforeTurnFrame:
        ctx = cast(BeforeTurnCtx, frame.slots[_CTX_SLOT])
        append_string_exports(
            ctx.extra_hints,
            collect_prefixed_slots(frame.slots, _EXTRA_HINT_PREFIX),
        )
        abort_reply = frame.slots.get(_ABORT_REPLY_SLOT)
        if isinstance(abort_reply, str) and abort_reply:
            ctx.abort = True
            ctx.abort_reply = abort_reply
        return frame


def default_before_turn_modules(
    bus: EventBus,
    session_manager: SessionManager,
    context_store: ContextStore,
    *,
    keep_count: int = 20,
    consolidator: MemoryConsolidator | None = None,
    plugin_modules: BeforeTurnModules | None = None,
) -> BeforeTurnModules:
    builtins: BeforeTurnModules = [
        _AcquireSessionModule(session_manager),
        _MemoryContextGuardModule(
            session_manager,
            keep_count,
            consolidator,
        ),
        _PrepareContextModule(context_store),
        _BuildBeforeTurnCtxModule(),
        _EmitBeforeTurnCtxModule(bus),
        _CollectBeforeTurnExportSlotsModule(),
        _ReturnBeforeTurnCtxModule(),
    ]
    return cast(
        BeforeTurnModules,
        topo_sort_modules(builtins + list(plugin_modules or [])),
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
