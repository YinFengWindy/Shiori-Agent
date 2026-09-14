from __future__ import annotations

from dataclasses import dataclass
import logging
from typing import TYPE_CHECKING, Awaitable, Callable, Protocol, TypeAlias, cast

from bus.event_bus import EventBus
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
from agent.core.passive_support import estimate_messages_tokens

if TYPE_CHECKING:
    from agent.core.passive_turn import ContextStore
    from session.manager import SessionManager

logger = logging.getLogger(__name__)


@dataclass
class BeforeTurnFrame(PhaseFrame[TurnState, BeforeTurnCtx]):
    pass


BeforeTurnModules: TypeAlias = list[PhaseModule[BeforeTurnFrame]]


class MemoryConsolidator(Protocol):
    """Schedules consolidation and exposes its last definitive failure."""

    def request_memory_consolidation(self, session_key: str) -> None: ...

    def get_memory_consolidation_failure(self, session_key: str) -> str | None: ...

    async def ensure_memory_consolidation(
        self, session_key: str, current_content: str = ""
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
        )
        frame.slots[_CONTEXT_BUNDLE_SLOT] = bundle
        return frame


class _MemoryContextGuardModule:
    slot = "before_turn.memory_context_guard"
    requires = ("before_turn.acquire_session", _SESSION_SLOT)
    produces = (_CTX_SLOT,)

    def __init__(
        self,
        keep_count: int,
        consolidator: MemoryConsolidator | None = None,
        input_token_threshold: int = 75000,
    ) -> None:
        self._keep_count = max(1, int(keep_count))
        self._min_new = max(5, self._keep_count // 2)
        self._threshold = self._keep_count + self._min_new
        self._input_token_threshold = max(0, int(input_token_threshold))
        self._consolidator = consolidator

    async def run(self, frame: BeforeTurnFrame) -> BeforeTurnFrame:
        if _CTX_SLOT in frame.slots:
            return frame
        state = frame.input
        if bool((state.msg.metadata or {}).get("skip_memory_context_guard")):
            return frame
        session = cast(SessionLike, frame.slots[_SESSION_SLOT])
        messages = list(getattr(session, "messages", []))
        last = _clamp_last_consolidated(
            getattr(session, "last_consolidated", 0),
            len(messages),
        )
        pending = len(messages) - last
        input_tokens = _estimate_session_input_tokens(session, state.msg.content, last)
        token_pressure = (
            self._input_token_threshold > 0
            and input_tokens >= self._input_token_threshold
        )
        if pending < self._threshold and not token_pressure:
            return frame

        if self._consolidator is not None:
            failure = self._consolidator.get_memory_consolidation_failure(
                state.session_key
            )
            if failure is not None:
                raise MemoryConsolidationFailedError(
                    f"记忆整理失败，请检查模型或网络配置后重试。详情：{failure}"
                )
            if token_pressure:
                ensure = getattr(
                    self._consolidator, "ensure_memory_consolidation", None
                )
                ensure_fn = cast("Callable[[str, str], Awaitable[bool]]", ensure)
                if not callable(ensure) or not await ensure_fn(
                    state.session_key, state.msg.content
                ):
                    raise MemoryConsolidationFailedError(
                        "记忆整理没有可处理的历史或未产生进展，已停止发送超限上下文。"
                    )
                input_tokens = _estimate_session_input_tokens(
                    session,
                    state.msg.content,
                    _clamp_last_consolidated(
                        getattr(session, "last_consolidated", 0),
                        len(getattr(session, "messages", [])),
                    ),
                )
                if input_tokens >= self._input_token_threshold:
                    raise MemoryConsolidationFailedError(
                        "记忆整理后输入仍超过预算，已停止发送超限上下文。"
                    )
            else:
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
    input_token_threshold: int = 75000,
    plugin_modules: BeforeTurnModules | None = None,
) -> BeforeTurnModules:
    builtins: BeforeTurnModules = [
        _AcquireSessionModule(session_manager),
        _MemoryContextGuardModule(
            keep_count,
            consolidator,
            input_token_threshold=input_token_threshold,
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


def _clamp_last_consolidated(value: object, total_messages: int) -> int:
    if isinstance(value, int):
        last = value
    elif isinstance(value, str):
        try:
            last = int(value)
        except ValueError:
            last = 0
    else:
        last = 0
    return min(max(0, last), max(0, int(total_messages)))


def _estimate_session_input_tokens(
    session: SessionLike,
    current_content: str,
    last_consolidated: int,
) -> int:
    """Estimate the next model input from unarchived history and current turn."""
    try:
        history = session.get_history(
            max_messages=500,
            start_index=last_consolidated,
        )
    except TypeError:
        history = session.get_history(max_messages=500)
    return estimate_messages_tokens(
        [*history, {"role": "user", "content": current_content}]
    )


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
