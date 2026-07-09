from __future__ import annotations

from dataclasses import dataclass
import logging
from typing import TYPE_CHECKING, Any, TypeAlias, cast

from agent.core.mood_resolver import resolve_role_mood
from agent.core.passive_support import update_session_runtime_metadata
from agent.core.response_parser import parse_response
from agent.lifecycle.phase import (
    PhaseFrame,
    PhaseModule,
    append_string_exports,
    collect_prefixed_slots,
    topo_sort_modules,
)
from agent.lifecycle.types import (
    AfterReasoningCtx,
    AfterReasoningInput,
    AfterReasoningResult,
)
from bus.event_bus import EventBus
from bus.events import OutboundMessage

if TYPE_CHECKING:
    from agent.looping.ports import LLMConfig, LLMServices
    from agent.looping.ports import SessionServices
    from session.manager import Session

logger = logging.getLogger(__name__)


@dataclass
class AfterReasoningFrame(PhaseFrame[AfterReasoningInput, AfterReasoningResult]):
    pass


AfterReasoningModules: TypeAlias = list[PhaseModule[AfterReasoningFrame]]


_CTX_SLOT = "reasoning:ctx"
_OUTBOUND_SLOT = "reasoning:outbound"
_PERSIST_USER_PREFIX = "persist:user:"
_PERSIST_ASSISTANT_PREFIX = "persist:assistant:"
_OUTBOUND_METADATA_PREFIX = "outbound:metadata:"
_OUTBOUND_MEDIA_PREFIX = "outbound:media:"
_ASSISTANT_FIXED_FIELDS = {"tools_used", "tool_chain", "reasoning_content"}
_USER_FIXED_FIELDS = {"media"}
_PERSISTED_USER_CONTENT_METADATA_KEY = "persisted_user_content"
_INTERNAL_USER_METADATA_KEYS = frozenset({_PERSISTED_USER_CONTENT_METADATA_KEY})
_CONVERSATION_MESSAGE_FIELDS = (
    "thread_id",
    "sender_role",
    "external_message_id",
    "delivery_status",
)


def _build_synced_message_metadata(
    *,
    channel: str,
    chat_id: str,
    metadata: dict[str, Any] | None,
) -> dict[str, Any]:
    next_metadata = dict(metadata or {})
    for key in _INTERNAL_USER_METADATA_KEYS:
        next_metadata.pop(key, None)
    if channel == "desktop":
        next_metadata.setdefault("source", "desktop")
    else:
        next_metadata.setdefault("source", "channel_sync")
        next_metadata.setdefault("context_channel", channel)
        next_metadata.setdefault("context_chat_id", chat_id)
        next_metadata.setdefault("transport_channel", channel)
        next_metadata.setdefault("transport_chat_id", chat_id)
    return next_metadata


def _copy_conversation_message_fields(
    *,
    metadata: dict[str, Any] | None,
    session: "Session",
) -> dict[str, Any]:
    source = dict(metadata or {})
    session_metadata = getattr(session, "metadata", None)
    if isinstance(session_metadata, dict):
        for field in _CONVERSATION_MESSAGE_FIELDS:
            source.setdefault(field, session_metadata.get(field))
    copied: dict[str, Any] = {}
    for field in _CONVERSATION_MESSAGE_FIELDS:
        value = source.get(field)
        if isinstance(value, str):
            value = value.strip()
        if value:
            copied[field] = value
    return copied


class _BuildAfterReasoningCtxModule:
    slot = "after_reasoning.build_ctx"
    requires: tuple[str, ...] = ()
    produces = (_CTX_SLOT,)

    async def run(self, frame: AfterReasoningFrame) -> AfterReasoningFrame:
        input = frame.input
        msg = input.state.msg
        turn_result = input.turn_result
        raw_reply = turn_result.reply
        if raw_reply is None:
            raw_reply = "I've completed processing but have no response to give."
        tool_chain = cast(list[dict[str, object]], turn_result.tool_chain)
        parsed = parse_response(raw_reply, tool_chain=tool_chain)
        frame.slots[_CTX_SLOT] = AfterReasoningCtx(
            session_key=input.state.session_key,
            channel=msg.channel,
            chat_id=msg.chat_id,
            reply=parsed.clean_text,
            response_metadata=parsed.metadata,
            tools_used=tuple(turn_result.tools_used),
            tool_chain=tuple(tool_chain),
            thinking=turn_result.thinking,
            streamed=turn_result.streamed,
            context_retry=dict(turn_result.context_retry),
            outbound_metadata={
                **(msg.metadata or {}),
                **input.state.extra_metadata,
                "tools_used": list(turn_result.tools_used),
                "tool_chain": list(tool_chain),
                "context_retry": dict(turn_result.context_retry),
                "streamed_reply": turn_result.streamed,
            },
        )
        return frame


class _EmitAfterReasoningCtxModule:
    slot = "after_reasoning.emit"
    requires = ("after_reasoning.build_ctx", _CTX_SLOT)
    produces = (_CTX_SLOT,)

    def __init__(self, bus: EventBus) -> None:
        self._bus = bus

    async def run(self, frame: AfterReasoningFrame) -> AfterReasoningFrame:
        ctx = cast(AfterReasoningCtx, frame.slots[_CTX_SLOT])
        frame.slots[_CTX_SLOT] = await self._bus.emit(ctx)
        return frame


class _ResolveMoodModule:
    slot = "after_reasoning.resolve_mood"
    requires = ("after_reasoning.emit", _CTX_SLOT)

    def __init__(self, llm: "LLMServices | None", llm_config: "LLMConfig | None") -> None:
        self._llm = llm
        self._llm_config = llm_config

    async def run(self, frame: AfterReasoningFrame) -> AfterReasoningFrame:
        ctx = cast(AfterReasoningCtx, frame.slots[_CTX_SLOT])
        if ctx.response_metadata.mood:
            return frame
        if self._llm is None or self._llm_config is None:
            return frame
        raw_session = frame.input.state.session
        if raw_session is None:
            return frame
        session = cast("Session", raw_session)
        runtime_config = session.metadata.get("role_runtime_config")
        if not isinstance(runtime_config, dict):
            return frame
        raw_bindings = runtime_config.get("mood_illustration_bindings")
        if not isinstance(raw_bindings, dict):
            return frame
        available_moods = [
            str(mood).strip()
            for mood, path in raw_bindings.items()
            if str(mood).strip() and str(path or "").strip()
        ]
        if not available_moods:
            return frame
        default_mood = str(runtime_config.get("default_mood") or "").strip() or available_moods[0]
        resolved_mood = await resolve_role_mood(
            self._llm.provider,
            model=self._llm_config.model,
            max_tokens=self._llm_config.max_tokens,
            reply_text=ctx.reply,
            available_moods=available_moods,
            default_mood=default_mood,
        )
        if resolved_mood:
            ctx.response_metadata.mood = resolved_mood
        return frame


class _PersistUserMessageModule:
    slot = "after_reasoning.persist_user"
    requires = ("after_reasoning.emit", _CTX_SLOT)

    def __init__(self, session_services: SessionServices) -> None:
        self._session_services = session_services

    async def run(self, frame: AfterReasoningFrame) -> AfterReasoningFrame:
        ctx = cast(AfterReasoningCtx, frame.slots[_CTX_SLOT])
        state = frame.input.state
        msg = state.msg
        raw_session = state.session
        if raw_session is None:
            raise RuntimeError("AfterReasoning requires TurnState.session")
        session = cast("Session", raw_session)
        omit_user_turn = bool((msg.metadata or {}).get("omit_user_turn"))
        if omit_user_turn:
            return frame
        if self._session_services.presence:
            self._session_services.presence.record_user_message(session.key)
        relationship_runtime = getattr(self._session_services, "relationship_runtime", None)
        if relationship_runtime is not None:
            relationship_runtime.handle_user_message(session.key)
        user_kwargs: dict[str, object] = {}
        user_kwargs["metadata"] = _build_synced_message_metadata(
            channel=msg.channel,
            chat_id=msg.chat_id,
            metadata=msg.metadata,
        )
        llm_user_content = ctx.context_retry.get("llm_user_content")
        if isinstance(llm_user_content, (str, list)):
            user_kwargs["llm_user_content"] = llm_user_content
        llm_context_frame = ctx.context_retry.get("llm_context_frame")
        if isinstance(llm_context_frame, str) and llm_context_frame.strip():
            user_kwargs["llm_context_frame"] = llm_context_frame
        user_kwargs.update(_collect_persist_user_slots(frame.slots))
        user_kwargs.update(
            _copy_conversation_message_fields(
                metadata=cast(dict[str, Any] | None, msg.metadata),
                session=session,
            )
        )
        persisted_user_content = msg.metadata.get(_PERSISTED_USER_CONTENT_METADATA_KEY)
        user_content = persisted_user_content if isinstance(persisted_user_content, str) else msg.content
        session.add_message(
            "user",
            user_content,
            media=msg.media if msg.media else None,
            **user_kwargs,
        )
        return frame


class _PersistAssistantMessageModule:
    slot = "after_reasoning.persist_asst"
    requires = ("after_reasoning.persist_user", _CTX_SLOT)

    async def run(self, frame: AfterReasoningFrame) -> AfterReasoningFrame:
        ctx = cast(AfterReasoningCtx, frame.slots[_CTX_SLOT])
        raw_session = frame.input.state.session
        if raw_session is None:
            raise RuntimeError("AfterReasoning requires TurnState.session")
        session = cast("Session", raw_session)
        assistant_kwargs: dict[str, Any] = {
            "tools_used": list(ctx.tools_used) if ctx.tools_used else None,
            "tool_chain": list(ctx.tool_chain) if ctx.tool_chain else None,
            "metadata": _build_synced_message_metadata(
                channel=ctx.channel,
                chat_id=ctx.chat_id,
                metadata=ctx.outbound_metadata,
            ),
        }
        if ctx.response_metadata.mood:
            assistant_kwargs["metadata"]["mood"] = ctx.response_metadata.mood
        if ctx.thinking is not None:
            assistant_kwargs["reasoning_content"] = ctx.thinking
        if ctx.media:
            assistant_kwargs["media"] = list(ctx.media)
        assistant_kwargs.update(_collect_persist_assistant_slots(frame.slots))
        assistant_kwargs.update(
            _copy_conversation_message_fields(
                metadata=ctx.outbound_metadata,
                session=session,
            )
        )
        session.add_message("assistant", ctx.reply, **assistant_kwargs)
        return frame


class _UpdateSessionMetadataModule:
    slot = "after_reasoning.update_meta"
    requires = ("after_reasoning.persist_asst", _CTX_SLOT)

    def __init__(self, relationship_runtime: Any | None = None) -> None:
        self._relationship_runtime = relationship_runtime

    async def run(self, frame: AfterReasoningFrame) -> AfterReasoningFrame:
        ctx = cast(AfterReasoningCtx, frame.slots[_CTX_SLOT])
        raw_session = frame.input.state.session
        if raw_session is None:
            raise RuntimeError("AfterReasoning requires TurnState.session")
        session = cast("Session", raw_session)
        update_session_runtime_metadata(
            session,
            tools_used=list(ctx.tools_used),
            tool_chain=list(ctx.tool_chain),
            mood=ctx.response_metadata.mood,
        )
        if self._relationship_runtime is not None:
            session.metadata = self._relationship_runtime.enrich_session_metadata(
                cast(dict[str, Any], session.metadata),
            )
        return frame


class _AppendMessagesModule:
    slot = "after_reasoning.append_messages"
    requires = ("after_reasoning.update_meta",)

    def __init__(self, session_services: SessionServices) -> None:
        self._session_services = session_services

    async def run(self, frame: AfterReasoningFrame) -> AfterReasoningFrame:
        state = frame.input.state
        raw_session = state.session
        if raw_session is None:
            raise RuntimeError("AfterReasoning requires TurnState.session")
        session = cast("Session", raw_session)
        persist_count = 1 if bool((state.msg.metadata or {}).get("omit_user_turn")) else 2
        await self._session_services.session_manager.append_messages(
            session,
            cast(list[dict[str, Any]], session.messages[-persist_count:]),
        )
        return frame


class _BuildOutboundMessageModule:
    slot = "after_reasoning.build_outbound"
    requires = ("after_reasoning.append_messages", _CTX_SLOT)
    produces = (_OUTBOUND_SLOT,)

    async def run(self, frame: AfterReasoningFrame) -> AfterReasoningFrame:
        ctx = cast(AfterReasoningCtx, frame.slots[_CTX_SLOT])
        metadata = dict(ctx.outbound_metadata)
        metadata.update(collect_prefixed_slots(frame.slots, _OUTBOUND_METADATA_PREFIX))
        media = list(ctx.media)
        _append_media(media, collect_prefixed_slots(frame.slots, _OUTBOUND_MEDIA_PREFIX))
        frame.slots[_OUTBOUND_SLOT] = OutboundMessage(
            channel=ctx.channel,
            chat_id=ctx.chat_id,
            content=ctx.reply,
            thinking=ctx.thinking,
            media=media,
            metadata=metadata,
        )
        return frame


class _ReturnAfterReasoningResultModule:
    slot = "after_reasoning.return"
    requires = ("after_reasoning.build_outbound", _CTX_SLOT, _OUTBOUND_SLOT)

    async def run(self, frame: AfterReasoningFrame) -> AfterReasoningFrame:
        frame.output = AfterReasoningResult(
            ctx=cast(AfterReasoningCtx, frame.slots[_CTX_SLOT]),
            outbound=cast(OutboundMessage, frame.slots[_OUTBOUND_SLOT]),
        )
        return frame


def default_after_reasoning_modules(
    bus: EventBus,
    session_services: SessionServices,
    llm: "LLMServices | None" = None,
    llm_config: "LLMConfig | None" = None,
    plugin_modules: AfterReasoningModules | None = None,
) -> AfterReasoningModules:
    resolved_llm = llm or cast(Any, None)
    resolved_llm_config = llm_config or cast(Any, None)
    relationship_runtime = getattr(session_services, "relationship_runtime", None)
    builtins: AfterReasoningModules = [
        _BuildAfterReasoningCtxModule(),
        _EmitAfterReasoningCtxModule(bus),
        _ResolveMoodModule(resolved_llm, resolved_llm_config),
        _PersistUserMessageModule(session_services),
        _PersistAssistantMessageModule(),
        _UpdateSessionMetadataModule(relationship_runtime),
        _AppendMessagesModule(session_services),
        _BuildOutboundMessageModule(),
        _ReturnAfterReasoningResultModule(),
    ]
    return cast(
        AfterReasoningModules,
        topo_sort_modules(builtins + list(plugin_modules or [])),
    )


def _collect_persist_assistant_slots(slots: dict[str, object]) -> dict[str, object]:
    return collect_prefixed_slots(
        slots,
        _PERSIST_ASSISTANT_PREFIX,
        reserved=_ASSISTANT_FIXED_FIELDS,
    )


def _collect_persist_user_slots(slots: dict[str, object]) -> dict[str, object]:
    return collect_prefixed_slots(
        slots,
        _PERSIST_USER_PREFIX,
        reserved=_USER_FIXED_FIELDS,
    )


def _append_media(target: list[str], exports: dict[str, object]) -> None:
    append_string_exports(target, exports)
