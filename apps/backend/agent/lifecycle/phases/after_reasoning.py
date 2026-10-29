from __future__ import annotations

from agent.turns.channel_sequence import channel_sequence_context
from agent.turns.channel_sequence_commit import commit_channel_reply_sequence

import logging
from typing import TYPE_CHECKING, Any, cast

from shiori_sdk.channels.message_source import (
    PERSISTED_USER_CONTENT_KEY,
    REPLY_TO_MEDIA_KEY,
    MessageSource,
)
from agent.core.passive_support import (
    build_session_runtime_metadata,
    update_session_runtime_metadata,
)
from session.manager.models import (
    CONTEXT_TURN_STARTED_AT,
    INTERRUPTED_TURN_METADATA_KEY,
    build_session_message,
)
from agent.core.citation import join_messages, take_citations
from agent.core.response_parser import ParsedResponse, ResponseMetadata, parse_response
from core.roles.reply_state import InvalidRoleReply, RoleReply, reply_state_metadata
from shiori_sdk.channels.chat_types import REPLY_MENTION_IDS_KEY, is_group_chat_type
from agent.core.turn_events import TurnEvents, read_only
from agent.lifecycle.types import (
    AfterReasoningCtx,
    AfterReasoningInput,
    AfterReasoningResult,
    TurnState,
)
from shiori_sdk.core.conversation import ReasoningFinished
from core.roles.affection_access import current_affection
from shiori_sdk.messages import OutboundMessage
from agent.turns.reply_sequence import ReplySequence
from agent.turns.reply_interruption import reply_was_invalidated
from agent.turns.reply_sequence_commit import (
    commit_invalidated_reply,
    commit_reply_sequence,
)

if TYPE_CHECKING:
    from bus.event_bus import EventBus
    from agent.looping.ports import SessionServices
    from session.manager import Session

logger = logging.getLogger(__name__)


_INTERNAL_USER_METADATA_KEYS = frozenset({PERSISTED_USER_CONTENT_KEY})
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


class AfterReasoningPhase:
    """Turns the reasoning's result into the committed reply and its outbound message.

    The steps run in this fixed order: build the reply context, take the
    citations and emit ``ReasoningFinished``, stage the user and assistant
    messages, update the session metadata, commit, then build the outbound
    message. A reply with a mood state, a reply sequence, an invalidated reply
    or turn pushes commits privately: its messages are drafts until the
    commit publishes them.
    """

    def __init__(
        self,
        bus: EventBus,
        events: TurnEvents,
        session_services: SessionServices,
    ) -> None:
        # The reply sequence commits announce ``ReplyMessageCommitted`` with
        # ``bus.emit``, a core domain event that does not go through the kernel.
        self._bus = bus
        self._events = events
        self._session_services = session_services
        self._relationship_runtime = getattr(
            session_services, "relationship_runtime", None
        )

    async def run(self, input: AfterReasoningInput) -> AfterReasoningResult:
        """Commits the reply and returns its context and outbound message."""
        state = input.state
        ctx, role_reply = _after_reasoning_ctx(input)
        previous_metadata = (
            dict(state.session.metadata) if state.session is not None else {}
        )
        private = (
            role_reply is not None
            or input.turn_result.reply_sequence is not None
            or reply_was_invalidated()
            or bool(state.turn_pushes and state.turn_pushes.messages)
        )
        cited = await self._emit(ctx)
        raw_session = state.session
        if raw_session is None:
            raise RuntimeError("AfterReasoning requires TurnState.session")
        session = cast("Session", raw_session)
        messages: list[dict[str, Any]] = []
        self._stage_user_message(ctx, state, session, messages, private=private)
        sequence = _stage_assistant_messages(
            ctx, input, session, messages, private=private, cited=cited
        )
        if private:
            metadata_updates = build_session_runtime_metadata(
                tools_used=list(ctx.tools_used),
                tool_chain=list(ctx.tool_chain),
            )
            attempted_metadata: dict[str, Any] = {}
        else:
            metadata_updates = {}
            attempted_metadata = self._update_session_metadata(ctx, session)
        await self._commit_messages(
            input,
            ctx,
            session,
            messages,
            private=private,
            role_reply=role_reply,
            sequence=sequence,
            metadata_updates=metadata_updates,
            previous_metadata=previous_metadata,
            attempted_metadata=attempted_metadata,
        )
        return AfterReasoningResult(ctx=ctx, outbound=_outbound_message(ctx, messages))

    async def _emit(self, ctx: AfterReasoningCtx) -> list[str]:
        """Takes the citations, emits ``ReasoningFinished`` and applies it to ``ctx``.

        Returns the cited memory IDs, stored with the assistant message.
        """
        cited = _take_citations(ctx)

        def apply(event: ReasoningFinished) -> None:
            ctx.reply = event.reply
            ctx.reply_messages = event.reply_messages
            ctx.media[:] = event.media
            ctx.meme_tag = event.meme_tag
            ctx.outbound_metadata = dict(event.outbound_metadata)

        await self._events.emit(_reasoning_finished(ctx), apply)
        return cited

    def _stage_user_message(
        self,
        ctx: AfterReasoningCtx,
        state: TurnState,
        session: Session,
        messages: list[dict[str, Any]],
        *,
        private: bool,
    ) -> None:
        msg = state.msg
        omit_user_turn = bool((msg.metadata or {}).get("omit_user_turn"))
        if omit_user_turn:
            return
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
        # Message time records receipt, not the eventual successful commit time.
        user_kwargs["timestamp"] = msg.timestamp.astimezone().isoformat()
        user_kwargs.update(
            _copy_conversation_message_fields(
                metadata=cast(dict[str, Any] | None, msg.metadata),
            )
        )
        if state.is_user_authored():
            self._record_user_activity(session.key)
        persisted_user_content = msg.metadata.get(PERSISTED_USER_CONTENT_KEY)
        user_content = (
            persisted_user_content
            if isinstance(persisted_user_content, str)
            else msg.content
        )
        # A quoted message's attachments lead the turn's media for the
        # model but stay the quote's: the stored message keeps only its own.
        # They are dropped by position, so a file the message itself
        # carries is kept even if it were the same file.
        quoted_media = msg.metadata.get(REPLY_TO_MEDIA_KEY)
        user_media = list(msg.media)[
            len(quoted_media) if isinstance(quoted_media, list) else 0 :
        ]
        if private:
            messages.append(
                build_session_message(
                    "user",
                    user_content,
                    media=user_media or None,
                    **user_kwargs,
                )
            )
        else:
            session.add_message(
                "user",
                user_content,
                media=user_media or None,
                **user_kwargs,
            )
            messages.append(session.messages[-1])

    def _record_user_activity(self, session_key: str) -> None:
        """用户本人发来消息：刷新在场，并让关系状态（孤独值、等待回复）响应。"""
        if self._session_services.presence:
            self._session_services.presence.record_user_message(session_key)
        affection = current_affection(self._relationship_runtime)
        if affection is not None:
            affection.handle_user_message(session_key)

    def _update_session_metadata(
        self, ctx: AfterReasoningCtx, session: Session
    ) -> dict[str, Any]:
        """Updates a publicly committed turn's session metadata in place.

        Returns the attempted metadata, which a failed commit restores from.
        """
        # A normally committed assistant reply closes any older interrupted snapshot.
        _ = session.metadata.pop(INTERRUPTED_TURN_METADATA_KEY, None)
        update_session_runtime_metadata(
            session,
            tools_used=list(ctx.tools_used),
            tool_chain=list(ctx.tool_chain),
            mood=None,
        )
        affection = current_affection(self._relationship_runtime)
        if affection is not None:
            session.metadata = affection.enrich_session_metadata(
                cast(dict[str, Any], session.metadata),
            )
        return dict(session.metadata)

    async def _commit_messages(
        self,
        input: AfterReasoningInput,
        ctx: AfterReasoningCtx,
        session: Session,
        owned_messages: list[dict[str, Any]],
        *,
        private: bool,
        role_reply: RoleReply | None,
        sequence: ReplySequence | None,
        metadata_updates: dict[str, Any],
        previous_metadata: dict[str, Any],
        attempted_metadata: dict[str, Any],
    ) -> None:
        state = input.state
        # Replies and embedded tool results stay in their triggering turn even
        # if an identity is bound while the model is running. Plugins cannot
        # override this host-owned timestamp through outgoing metadata.
        for message in owned_messages:
            message.setdefault("metadata", {})[
                CONTEXT_TURN_STARTED_AT
            ] = state.msg.timestamp.isoformat()

        def enrich(metadata: dict[str, Any]) -> dict[str, Any]:
            affection = current_affection(self._relationship_runtime)
            if affection is None:
                return metadata
            return affection.enrich_session_metadata(metadata)

        state_kwargs = (
            {
                "metadata_updates": metadata_updates,
                "pending_messages": True,
                "removed_metadata_keys": (INTERRUPTED_TURN_METADATA_KEY,),
                "metadata_enricher": enrich,
            }
            if private
            else {}
        )
        if role_reply is not None:
            # Only a freshly fetched mood/thought bumps session mood state; a
            # degraded reply (mood call failed) leaves last turn's mood and
            # thought untouched instead of overwriting them with copies.
            mood_fresh = bool(input.turn_result.role_reply_mood_fresh)
            state_kwargs = {
                "metadata_updates": {
                    **metadata_updates,
                    **(
                        reply_state_metadata(
                            role_reply,
                            updated_at=str(metadata_updates["last_turn_ts"]),
                        )
                        if mood_fresh
                        else {}
                    ),
                },
                "pending_messages": True,
                "removed_metadata_keys": (INTERRUPTED_TURN_METADATA_KEY,),
                "metadata_enricher": enrich,
                "expected_mood_updated_at": str(
                    input.turn_result.context_retry.get(
                        "role_reply_previous_updated_at",
                        previous_metadata.get("current_mood_updated_at", ""),
                    )
                ),
            }
        try:
            if sequence is not None and reply_was_invalidated():
                await commit_invalidated_reply(
                    manager=self._session_services.session_manager,
                    bus=self._bus,
                    session=session,
                    messages=owned_messages,
                    sequence=sequence,
                    desktop=state.msg.channel == "desktop",
                    on_first_commit=(
                        state.turn_pushes.committed
                        if state.turn_pushes is not None
                        else None
                    ),
                )
            if sequence is not None and state.msg.channel != "desktop":
                await commit_channel_reply_sequence(
                    manager=self._session_services.session_manager,
                    session=session,
                    messages=owned_messages,
                    sequence=sequence,
                    state_kwargs=state_kwargs,
                    metadata=dict(ctx.outbound_metadata),
                    channel=ctx.channel,
                    chat_id=ctx.chat_id,
                    on_first_commit=(
                        state.turn_pushes.committed
                        if state.turn_pushes is not None
                        else None
                    ),
                )
                state.dispatch_outbound = False
            elif sequence is not None:
                await commit_reply_sequence(
                    manager=self._session_services.session_manager,
                    bus=self._bus,
                    session=session,
                    messages=owned_messages,
                    sequence=sequence,
                    state_kwargs=state_kwargs,
                    on_first_commit=(
                        state.turn_pushes.committed
                        if state.turn_pushes is not None
                        else None
                    ),
                )
            else:
                await self._session_services.session_manager.append_messages(
                    session,
                    owned_messages,
                    **state_kwargs,
                )
            if private:
                state.session = self._session_services.session_manager.get_or_create(
                    session.key
                )
        except BaseException:
            if private:
                # Drafts were private; cancellation before lock acquisition publishes nothing.
                raise
            # Only remove this turn's objects; unrelated concurrent messages remain.
            session.messages[:] = [
                message
                for message in session.messages
                if not any(message is owned for owned in owned_messages)
            ]
            if session.metadata.get("last_turn_ts") == attempted_metadata.get(
                "last_turn_ts"
            ):
                for key in (
                    "last_turn_tool_calls_count",
                    "last_turn_ts",
                    INTERRUPTED_TURN_METADATA_KEY,
                ):
                    if key in previous_metadata:
                        session.metadata[key] = previous_metadata[key]
                    else:
                        session.metadata.pop(key, None)
            raise
        state.committed_message_ids = tuple(
            str(message["id"]) for message in owned_messages if message.get("id")
        )
        if (
            role_reply is not None
            and role_reply.affection is not None
            and state.is_user_turn()
        ):
            # Only the user's own message counts (group members and scheduled
            # jobs do not; proactive replies never pass here), and only once
            # the reply is committed: a stale or failed commit raised above.
            # AfterTurn applies it, so bookkeeping cannot block delivery.
            state.affection_change = role_reply.affection
        if state.turn_pushes is not None:
            await state.turn_pushes.committed()


def _after_reasoning_ctx(
    input: AfterReasoningInput,
) -> tuple[AfterReasoningCtx, RoleReply | None]:
    """The reply's context and, for a formal role reply, its mood state."""
    msg = input.state.msg
    turn_result = input.turn_result
    raw_reply = turn_result.reply
    if raw_reply is None:
        raw_reply = "I've completed processing but have no response to give."
    tool_chain = cast(list[dict[str, object]], turn_result.tool_chain)
    session = input.state.session
    mention_ids: tuple[str, ...] = ()
    role_reply: RoleReply | None = None
    if reply_was_invalidated():
        parsed = ParsedResponse(clean_text="", metadata=ResponseMetadata(raw_text=""))
    elif session is not None and turn_result.context_retry.get("formal_role_reply"):
        # The reasoner already produced content plus a validated (or
        # degraded, previous-turn) RoleReply; no JSON parsing here. Kept
        # off `context_retry`, which gets snapshotted verbatim into
        # persisted JSON metadata further down.
        if not isinstance(turn_result.role_reply, RoleReply):
            raise InvalidRoleReply("角色回复缺少已生成的心情/想法状态")
        role_reply = turn_result.role_reply
        # Mentions belong to group replies only; no other reply carries them.
        if is_group_chat_type((msg.metadata or {}).get("chat_type")):
            mention_ids = role_reply.mention_ids
        parsed = ParsedResponse(
            clean_text=role_reply.content,
            metadata=ResponseMetadata(
                raw_text=raw_reply, mood=role_reply.mood, thought=role_reply.thought
            ),
        )
    else:
        parsed = parse_response(raw_reply, tool_chain=tool_chain)
    if turn_result.raw_reply is not None and not reply_was_invalidated():
        parsed.metadata.raw_text = turn_result.raw_reply
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
    ctx = AfterReasoningCtx(
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
            # Extra group members the role chose to mention in this reply.
            **({REPLY_MENTION_IDS_KEY: list(mention_ids)} if mention_ids else {}),
        },
    )
    sequence = turn_result.reply_sequence
    if isinstance(sequence, ReplySequence) and not reply_was_invalidated():
        ctx.reply_messages = sequence.messages
        ctx.reply = sequence.content
    return ctx, role_reply


def _take_citations(ctx: AfterReasoningCtx) -> list[str]:
    """Removes the citation markers before the plugins see the reply (D9).

    Returns the cited memory IDs, stored with the assistant message. The
    leftover tags are removed by the core check after ``ReasoningFinished``.
    """
    messages, cited = take_citations(ctx.reply_messages or (ctx.reply,), ctx.tool_chain)
    if ctx.reply_messages:
        ctx.reply_messages = messages
        ctx.reply = join_messages(messages)
    else:
        ctx.reply = messages[0]
    return cited


def _reasoning_finished(ctx: AfterReasoningCtx) -> ReasoningFinished:
    """The ``ReasoningFinished`` projection of the reply's context."""
    return ReasoningFinished(
        session_key=ctx.session_key,
        channel=ctx.channel,
        chat_id=ctx.chat_id,
        tools_used=ctx.tools_used,
        tool_chain=tuple(read_only(group) for group in ctx.tool_chain),
        thinking=ctx.thinking,
        streamed=ctx.streamed,
        reply=ctx.reply,
        reply_messages=ctx.reply_messages,
        media=tuple(ctx.media),
        meme_tag=ctx.meme_tag,
        outbound_metadata=read_only(ctx.outbound_metadata),
    )


def _stage_assistant_messages(
    ctx: AfterReasoningCtx,
    input: AfterReasoningInput,
    session: Session,
    messages: list[dict[str, Any]],
    *,
    private: bool,
    cited: list[str],
) -> ReplySequence | None:
    """Stages the assistant reply; returns the reply sequence it commits as, if any."""
    drafts = input.state.turn_pushes
    if drafts is not None:
        messages.extend(drafts.messages)
    carried = input.turn_result.reply_sequence
    sequence: ReplySequence | None = None
    if isinstance(carried, ReplySequence) or reply_was_invalidated():
        if not ctx.outbound_metadata.get("turn_id") and not (
            channel_sequence_context() is not None
            and ctx.outbound_metadata.get("request_id")
        ):
            raise ValueError("消息序列需要可投递的交互回合标识")
        if reply_was_invalidated():
            sequence = ReplySequence(("",))
        else:
            decorated = ctx.reply_messages or cast(ReplySequence, carried).messages
            sequence = ReplySequence(tuple(decorated))
        ctx.reply = sequence.content
        ctx.reply_messages = sequence.messages
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
    if ctx.media:
        assistant_kwargs["media"] = list(dict.fromkeys(ctx.media))
    if cited:
        assistant_kwargs["cited_memory_ids"] = cited
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
        )
    )
    if sequence is not None:
        for index, content in enumerate(sequence.messages):
            metadata = {
                **assistant_metadata,
                "reply_sequence_id": assistant_metadata.get("turn_id")
                or assistant_metadata["request_id"],
                "reply_sequence_index": index,
            }
            kwargs = dict(assistant_kwargs)
            if index:
                for key in (
                    "tools_used",
                    "tool_chain",
                    "reasoning_content",
                    "media",
                ):
                    kwargs.pop(key, None)
                for key in (
                    "turn_metrics",
                    "tools_used",
                    "tool_chain",
                    "context_retry",
                    REPLY_MENTION_IDS_KEY,
                ):
                    metadata.pop(key, None)
            if index < len(sequence.messages) - 1:
                metadata.pop("mood", None)
                metadata.pop("thought", None)
            kwargs["metadata"] = metadata
            messages.append(build_session_message("assistant", content, **kwargs))
    elif private:
        messages.append(
            build_session_message("assistant", ctx.reply, **assistant_kwargs)
        )
    else:
        session.add_message("assistant", ctx.reply, **assistant_kwargs)
        messages.append(session.messages[-1])
    return sequence


def _outbound_message(
    ctx: AfterReasoningCtx, owned_messages: list[dict[str, Any]]
) -> OutboundMessage:
    """The reply's outbound message, pointing at its committed row."""
    # The commit mutated the assistant reply's dict in place with the
    # store-assigned id. Carrying that id lets delivery bookkeeping target this
    # exact row later on.
    committed_message_id = (
        str(owned_messages[-1].get("id") or "").strip() if owned_messages else ""
    )
    return OutboundMessage(
        channel=ctx.channel,
        chat_id=ctx.chat_id,
        content=ctx.reply,
        thinking=ctx.thinking,
        media=list(ctx.media),
        metadata=dict(ctx.outbound_metadata),
        committed_message_id=committed_message_id or None,
    )
