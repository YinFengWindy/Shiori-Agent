from __future__ import annotations

from dataclasses import dataclass
import logging
from typing import TYPE_CHECKING, Any, Awaitable, Callable, Protocol, TypeAlias, cast

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
    from agent.looping.ports import SessionServices
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


_PERSISTED_USER_MESSAGE_SLOT = "session:persisted_user_message"


class _PersistPendingUserMessageModule:
    """在拿到 session 之后立刻落库用户消息（issue #306）。

    一处覆盖所有失败路径：本模块之后任何一步失败——包括
    _MemoryContextGuardModule 自己的记忆整理门禁（粘滞失败、token 超限，
    也包括 consolidator=None 时不抛异常、只产出 abort 的路径）、
    before_reasoning 窗口内的取消（含记忆检索、prompt warmup，这段窗口内的
    CancelledError 是 BaseException，任何 except Exception 都接不住）、
    reasoning/AfterReasoning 失败——用户这句话都已经落库；助手侧仍然只在
    成功提交时落库。见 persist_pending_user_message() 的完整说明。

    诚实记录一个行为差异（不是缺陷，是本工单修复数据丢失的固有代价）：
    在这个改动之前，失败的回合什么都不落库，pending 计数不会因为失败回合
    增长；现在失败回合也会落库用户消息，pending 会照常增长。对于反复失败
    的会话（例如 provider 持续报错），_MemoryContextGuardModule 和背后的
    记忆整理会比修复前更早触发——这是正确的行为（这些消息本来就该被算进
    历史），但触发时机确实会变。本模块只保证"同样的历史规模下触发判断不变"
    （_historical_messages() 显式排除当轮刚落库的消息，见下方），不保证
    "同样多轮失败对话下触发时机不变"。
    """

    slot = "before_turn.persist_user"
    requires = ("before_turn.acquire_session", _SESSION_SLOT)
    produces = (_PERSISTED_USER_MESSAGE_SLOT,)

    def __init__(self, session_services: "SessionServices") -> None:
        self._session_services = session_services

    async def run(self, frame: BeforeTurnFrame) -> BeforeTurnFrame:
        # 延迟导入：after_reasoning.py 所在的 agent.lifecycle.phases 包
        # __init__.py 会先加载 after_reasoning，其导入链经
        # agent.core.passive_support -> agent.core.passive_turn.pipeline ->
        # reasoner 再回到本文件；如果在模块顶层导入
        # persist_pending_user_message，会在这条链的中途形成循环导入。函数体
        # 内导入把它推迟到真正调用时（届时两个模块都已加载完毕），不改变任何
        # 运行时行为。
        from agent.lifecycle.phases.after_reasoning import persist_pending_user_message

        state = frame.input
        state.persisted_user_message = await persist_pending_user_message(
            state, self._session_services
        )
        frame.slots[_PERSISTED_USER_MESSAGE_SLOT] = state.persisted_user_message
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


def _historical_messages(
    session: SessionLike,
    current_turn_message: dict[str, Any] | None,
) -> tuple[list[dict[str, Any]], bool]:
    """返回排除掉"当轮已落库用户消息"之后的 session.messages，以及是否排除了。

    Issue #306：用户消息现在会在 before_turn 拿到 session 之后立刻落库
    （_PersistPendingUserMessageModule），本模块运行时它已经是
    session.messages 的最后一条。本模块的 pending/token 统计语义是"历史 +
    当轮尚未计入的新消息"，如果不排除就会把同一条消息算两次、让 pending
    比早落库之前多 1、token 估算也多算一份——不是"表现不变"，是把同一条消息
    数了两遍。这里显式排除它，让触发条件在同样的历史规模下与早落库之前完全
    一致（新增测试
    test_memory_context_guard_trigger_turn_unchanged_by_early_persist 验证了
    这一点）。
    """
    messages = list(getattr(session, "messages", []))
    if (
        current_turn_message is not None
        and messages
        and messages[-1] is current_turn_message
    ):
        return messages[:-1], True
    return messages, False


class _MemoryContextGuardModule:
    slot = "before_turn.memory_context_guard"
    requires = (
        "before_turn.acquire_session",
        "before_turn.persist_user",
        _SESSION_SLOT,
    )
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
        messages, current_turn_persisted = _historical_messages(
            session, state.persisted_user_message
        )
        last = _clamp_last_consolidated(
            getattr(session, "last_consolidated", 0),
            len(messages),
        )
        pending = len(messages) - last
        input_tokens = _estimate_session_input_tokens(
            session,
            state.msg.content,
            last,
            current_turn_already_persisted=current_turn_persisted,
        )
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
                refreshed_messages, refreshed_current_turn_persisted = (
                    _historical_messages(session, state.persisted_user_message)
                )
                input_tokens = _estimate_session_input_tokens(
                    session,
                    state.msg.content,
                    _clamp_last_consolidated(
                        getattr(session, "last_consolidated", 0),
                        len(refreshed_messages),
                    ),
                    current_turn_already_persisted=refreshed_current_turn_persisted,
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
    session_services: "SessionServices | None" = None,
    plugin_modules: BeforeTurnModules | None = None,
) -> BeforeTurnModules:
    builtins: BeforeTurnModules = [
        _AcquireSessionModule(session_manager),
        *(
            [_PersistPendingUserMessageModule(session_services)]
            if session_services is not None
            else []
        ),
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
    *,
    current_turn_already_persisted: bool = False,
) -> int:
    """Estimate the next model input from unarchived history and current turn.

    `last_consolidated` is computed by the caller against the *historical*
    message count (current-turn message excluded, see `_historical_messages`).
    `session.get_history()` still reads the real `session.messages`, so when
    the current turn was already persisted (issue #306 早落库) it comes back
    as the last history entry; drop it here and re-append the exact same
    synthetic `current_content` message used before that persist moved
    earlier, so the token estimate is byte-identical to the pre-#306 formula
    for the same underlying history and current turn.
    """
    try:
        history = session.get_history(
            max_messages=500,
            start_index=last_consolidated,
        )
    except TypeError:
        history = session.get_history(max_messages=500)
    if current_turn_already_persisted and history and history[-1].get("role") == "user":
        history = history[:-1]
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
