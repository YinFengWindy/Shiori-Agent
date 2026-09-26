from __future__ import annotations

from dataclasses import dataclass
import logging
from typing import TYPE_CHECKING, Any, TypeAlias, cast

from core.common.message_source import MessageSource
from agent.core.passive_support import (
    build_session_runtime_metadata,
    update_session_runtime_metadata,
)
from session.manager.models import INTERRUPTED_TURN_METADATA_KEY, build_session_message
from agent.core.response_parser import parse_response, ParsedResponse, ResponseMetadata
from core.roles.reply_state import InvalidRoleReply, RoleReply, reply_state_metadata
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
        session = input.state.session
        if session is not None and turn_result.context_retry.get("formal_role_reply"):
            # The reasoner already produced content plus a validated (or
            # degraded, previous-turn) RoleReply; no JSON parsing here. Kept
            # off `context_retry`, which gets snapshotted verbatim into
            # persisted JSON metadata further down.
            if not isinstance(turn_result.role_reply, RoleReply):
                raise InvalidRoleReply("角色回复缺少已生成的心情/想法状态")
            reply = turn_result.role_reply
            parsed = ParsedResponse(
                clean_text=reply.content,
                metadata=ResponseMetadata(
                    raw_text=raw_reply, mood=reply.mood, thought=reply.thought
                ),
            )
            frame.slots["reply:state"] = reply
        else:
            parsed = parse_response(raw_reply, tool_chain=tool_chain)
        if session is not None:
            frame.slots["reply:previous_metadata"] = dict(session.metadata)
            frame.slots["reply:messages"] = []
            frame.slots["reply:private"] = "reply:state" in frame.slots or bool(
                input.state.desktop_pushes and input.state.desktop_pushes.messages
            )
        raw_turn_metrics = turn_result.context_retry.get("turn_metrics")
        turn_metrics = (
            {
                key: value
                for key in ("total_tokens", "thinking_duration_ms")
                if isinstance((value := raw_turn_metrics.get(key)), int) and value >= 0
            }
            if isinstance(raw_turn_metrics, dict)
            else {}
        )
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
                **(
                    {"account_delivery_sent": True}
                    if turn_result.context_retry.get("account_delivery_sent")
                    else {}
                ),
                **({"turn_metrics": turn_metrics} if turn_metrics else {}),
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
        relationship_runtime = getattr(
            self._session_services, "relationship_runtime", None
        )
        if relationship_runtime is not None:
            relationship_runtime.handle_user_message(session.key)
        user_kwargs: dict[str, object] = {}
        user_metadata = _build_synced_message_metadata(
            channel=msg.channel,
            chat_id=msg.chat_id,
            metadata=msg.metadata,
        )
        user_metadata["message_source"] = MessageSource.from_inbound(msg).to_metadata()
        user_kwargs["metadata"] = user_metadata
        llm_user_content = ctx.context_retry.get("llm_user_content")
        if isinstance(llm_user_content, (str, list)):
            user_kwargs["llm_user_content"] = llm_user_content
        llm_context_frame = ctx.context_retry.get("llm_context_frame")
        if isinstance(llm_context_frame, str) and llm_context_frame.strip():
            user_kwargs["llm_context_frame"] = llm_context_frame
        user_kwargs.update(_collect_persist_user_slots(frame.slots))
        # Message time records receipt, not the eventual successful commit time.
        user_kwargs["timestamp"] = msg.timestamp.astimezone().isoformat()
        user_kwargs.update(
            _copy_conversation_message_fields(
                metadata=cast(dict[str, Any] | None, msg.metadata),
                session=session,
            )
        )
        persisted_user_content = msg.metadata.get(_PERSISTED_USER_CONTENT_METADATA_KEY)
        user_content = (
            persisted_user_content
            if isinstance(persisted_user_content, str)
            else msg.content
        )
        if frame.slots["reply:private"]:
            frame.slots["reply:messages"].append(
                build_session_message(
                    "user",
                    user_content,
                    media=msg.media if msg.media else None,
                    **user_kwargs,
                )
            )
        else:
            session.add_message(
                "user",
                user_content,
                media=msg.media if msg.media else None,
                **user_kwargs,
            )
            frame.slots["reply:messages"].append(session.messages[-1])
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
        drafts = frame.input.state.desktop_pushes
        if drafts is not None:
            frame.slots["reply:messages"].extend(drafts.messages)
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
        if ctx.response_metadata.thought:
            assistant_kwargs["metadata"]["thought"] = ctx.response_metadata.thought
        if ctx.thinking is not None:
            assistant_kwargs["reasoning_content"] = ctx.thinking
        persisted_media = list(dict.fromkeys([*ctx.media, *ctx.persisted_media]))
        if persisted_media:
            assistant_kwargs["media"] = persisted_media
        assistant_kwargs.update(_collect_persist_assistant_slots(frame.slots))
        # Outbound transport metadata still identifies the triggering turn for
        # live-stream correlation. Persist that identity separately: the reply's
        # own platform ID is only known after the channel acknowledges delivery.
        assistant_metadata = assistant_kwargs["metadata"]
        trigger_id = assistant_metadata.pop("external_message_id", None)
        if trigger_id:
            assistant_metadata["trigger_external_message_id"] = trigger_id
        assistant_metadata.pop("delivery_status", None)
        assistant_kwargs.update(
            _copy_conversation_message_fields(
                metadata=assistant_metadata,
                session=session,
            )
        )
        if frame.slots["reply:private"]:
            frame.slots["reply:messages"].append(
                build_session_message("assistant", ctx.reply, **assistant_kwargs)
            )
        else:
            session.add_message("assistant", ctx.reply, **assistant_kwargs)
            frame.slots["reply:messages"].append(session.messages[-1])
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
        if frame.slots["reply:private"]:
            frame.slots["reply:metadata_updates"] = build_session_runtime_metadata(
                tools_used=list(ctx.tools_used),
                tool_chain=list(ctx.tool_chain),
            )
            return frame
        # A normally committed assistant reply closes any older interrupted snapshot.
        _ = session.metadata.pop(INTERRUPTED_TURN_METADATA_KEY, None)
        update_session_runtime_metadata(
            session,
            tools_used=list(ctx.tools_used),
            tool_chain=list(ctx.tool_chain),
            mood=None,
        )
        if self._relationship_runtime is not None:
            session.metadata = self._relationship_runtime.enrich_session_metadata(
                cast(dict[str, Any], session.metadata),
            )
        frame.slots["reply:attempted_metadata"] = dict(session.metadata)
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
        owned_messages = frame.slots["reply:messages"]
        reply = frame.slots.get("reply:state")
        relationship_runtime = getattr(
            self._session_services, "relationship_runtime", None
        )
        state_kwargs = (
            {
                "metadata_updates": frame.slots["reply:metadata_updates"],
                "pending_messages": True,
                "removed_metadata_keys": (INTERRUPTED_TURN_METADATA_KEY,),
                "metadata_enricher": (
                    relationship_runtime.enrich_session_metadata
                    if relationship_runtime is not None
                    else None
                ),
            }
            if frame.slots["reply:private"]
            else {}
        )
        if reply is not None:
            pending_metadata = frame.slots["reply:metadata_updates"]
            # Only a freshly fetched mood/thought bumps session mood state; a
            # degraded reply (mood call failed) leaves last turn's mood and
            # thought untouched instead of overwriting them with copies.
            mood_fresh = bool(frame.input.turn_result.role_reply_mood_fresh)
            state_kwargs = {
                "metadata_updates": {
                    **pending_metadata,
                    **(
                        reply_state_metadata(
                            reply, updated_at=str(pending_metadata["last_turn_ts"])
                        )
                        if mood_fresh
                        else {}
                    ),
                },
                "pending_messages": True,
                "removed_metadata_keys": (INTERRUPTED_TURN_METADATA_KEY,),
                "metadata_enricher": (
                    relationship_runtime.enrich_session_metadata
                    if relationship_runtime is not None
                    else None
                ),
                "expected_mood_updated_at": str(
                    frame.input.turn_result.context_retry.get(
                        "role_reply_previous_updated_at",
                        frame.slots["reply:previous_metadata"].get(
                            "current_mood_updated_at", ""
                        ),
                    )
                ),
            }
        try:
            await self._session_services.session_manager.append_messages(
                session,
                owned_messages,
                **state_kwargs,
            )
            if frame.slots["reply:private"]:
                state.session = self._session_services.session_manager.get_or_create(
                    session.key
                )
        except BaseException:
            if frame.slots["reply:private"]:
                # Drafts were private; cancellation before lock acquisition publishes nothing.
                raise
            # Only remove this turn's objects; unrelated concurrent messages remain.
            session.messages[:] = [
                message
                for message in session.messages
                if not any(message is owned for owned in owned_messages)
            ]
            previous = frame.slots["reply:previous_metadata"]
            attempted = frame.slots["reply:attempted_metadata"]
            if session.metadata.get("last_turn_ts") == attempted.get("last_turn_ts"):
                for key in (
                    "last_turn_tool_calls_count",
                    "last_turn_ts",
                    INTERRUPTED_TURN_METADATA_KEY,
                ):
                    if key in previous:
                        session.metadata[key] = previous[key]
                    else:
                        session.metadata.pop(key, None)
            raise
        state.committed_message_ids = tuple(
            str(message["id"]) for message in owned_messages if message.get("id")
        )
        if state.desktop_pushes is not None:
            await state.desktop_pushes.committed()
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
        _append_media(
            media, collect_prefixed_slots(frame.slots, _OUTBOUND_MEDIA_PREFIX)
        )
        # after_reasoning.append_messages already committed the assistant reply;
        # its dict was mutated in place with the store-assigned id. Carrying that
        # id lets delivery bookkeeping target this exact row later on.
        owned_messages = frame.slots.get("reply:messages") or []
        committed_message_id = (
            str(owned_messages[-1].get("id") or "").strip() if owned_messages else ""
        )
        frame.slots[_OUTBOUND_SLOT] = OutboundMessage(
            channel=ctx.channel,
            chat_id=ctx.chat_id,
            content=ctx.reply,
            thinking=ctx.thinking,
            media=media,
            metadata=metadata,
            committed_message_id=committed_message_id or None,
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
    relationship_runtime = getattr(session_services, "relationship_runtime", None)
    builtins: AfterReasoningModules = [
        _BuildAfterReasoningCtxModule(),
        _EmitAfterReasoningCtxModule(bus),
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
