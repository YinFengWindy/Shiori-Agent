from __future__ import annotations

import copy
import logging
from typing import TYPE_CHECKING, Any, cast

from agent.core.passive_support import (
    build_post_reply_context_budget,
    extract_react_stats,
    log_post_reply_context_budget,
    log_react_context_budget,
)
from agent.core.types import to_tool_call_groups
from conversation.context_scope import history_filter
from agent.lifecycle.types import TurnSnapshot, TurnState
from agent.core.turn_events import TurnEvents
from shiori_sdk.core.conversation import TurnFinished
from agent.turns.outbound import OutboundDispatch, OutboundPort
from bus.event_bus import EventBus
from shiori_sdk.messages import OutboundMessage
from bus.events_lifecycle import NOT_USER_AUTHORED_KEY, SKIP_POST_MEMORY_KEY
from shiori_sdk.memory.committed import TurnCommitted
from core.roles.affection_access import current_affection

if TYPE_CHECKING:
    from agent.context import ContextBuilder
    from session.manager import Session

logger = logging.getLogger(__name__)


def will_dispatch_outbound(snapshot: TurnSnapshot) -> bool:
    """Share the actual normal-reply decision with pre-dispatch observers."""
    return snapshot.state.dispatch_outbound and not snapshot.outbound.metadata.get(
        "account_delivery_sent"
    )


class AfterTurnPhase:
    """Closes a committed turn and dispatches its reply.

    The steps run in this fixed order: measure the post-reply context, apply
    the reply's affection change, fan ``TurnCommitted`` out, log the budgets,
    emit ``TurnFinished``, then dispatch.
    """

    def __init__(
        self,
        bus: EventBus,
        events: TurnEvents,
        outbound: OutboundPort,
        context: ContextBuilder,
        history_window: int = 500,
        relationship_runtime: object | None = None,
    ) -> None:
        # ``TurnCommitted`` is a core domain event, not a turn event: it fans
        # out on the core bus alone, without the plugin kernel.
        self._bus = bus
        self._events = events
        self._outbound = outbound
        self._context = context
        self._history_window = max(1, int(history_window))
        self._relationship_runtime = relationship_runtime

    async def run(self, snap: TurnSnapshot) -> OutboundMessage:
        """Closes the turn and returns its outbound message."""
        state = snap.state
        raw_session = state.session
        if raw_session is None:
            raise RuntimeError("AfterTurn requires TurnState.session")
        session = cast("Session", raw_session)
        hw = self._history_window
        budget = build_post_reply_context_budget(
            context=self._context,
            history=session.get_history(
                max_messages=hw,
                include=history_filter(state.context_view),
            ),
            history_window=hw,
        )
        react_stats = extract_react_stats(snap.ctx.context_retry)
        await _apply_turn_affection(self._relationship_runtime, state)
        await self._bus.fanout(
            _turn_committed(snap, budget=budget, react_stats=react_stats)
        )
        log_post_reply_context_budget(session_key=state.session_key, budget=budget)
        log_react_context_budget(session_key=state.session_key, react_stats=react_stats)
        # Nothing is writable: the turn is stored, only listeners remain.
        await self._events.emit(_turn_finished(snap), lambda _: None)
        await _dispatch(self._outbound, snap)
        return snap.outbound


def _memory_extra(state: TurnState) -> dict[str, object]:
    """``TurnCommitted.extra`` 的记忆标记（含义见 ``bus.events_lifecycle``）。

    群友、陌生人的回合不给记忆引擎抽取，免得他们的发言被当成用户的画像与偏好
    证据；用户本人的回合（包括在群里的）照常抽取。
    """
    if (state.msg.metadata or {}).get(SKIP_POST_MEMORY_KEY):
        return {SKIP_POST_MEMORY_KEY: True}
    if not state.is_user_authored():
        return {SKIP_POST_MEMORY_KEY: True, NOT_USER_AUTHORED_KEY: True}
    return {}


async def _apply_turn_affection(
    relationship_runtime: object | None, state: TurnState
) -> None:
    """Applies the committed reply's affection change before the turn is announced.

    Running ahead of ``TurnCommitted`` lets every session refresh triggered by
    it carry the new summary.
    """
    change = state.affection_change
    affection = current_affection(relationship_runtime)
    if change is None or affection is None:
        return
    session = cast("Session", state.session)
    try:
        await affection.apply_turn_affection(
            session.key, delta=change.delta, reason=change.reason
        )
    except Exception:
        # Boundary: the reply is already committed and goes out regardless;
        # affection is a side record of it. Raising here would report a
        # stored reply as failed (desktop shows a retry error), so the
        # failure is logged with its traceback instead.
        logger.exception(
            "好感记账失败，本轮回复照常完成: session=%s role=%s change=%+d",
            session.key,
            session.metadata.get("role_id"),
            change.delta,
        )


def _turn_committed(
    snap: TurnSnapshot,
    *,
    budget: dict[str, int],
    react_stats: dict[str, int],
) -> TurnCommitted:
    """The ``TurnCommitted`` record of the committed turn."""
    state = snap.state
    msg = state.msg
    session = cast("Session", state.session)
    role_id = str(session.metadata.get("role_id") or "").strip()
    tool_chain_list = cast(list[dict[str, Any]], list(snap.ctx.tool_chain))
    omit_user_turn = bool((msg.metadata or {}).get("omit_user_turn"))
    source = str((msg.metadata or {}).get("source") or "").strip()
    raw_turn_metrics = snap.ctx.outbound_metadata.get("turn_metrics")
    turn_metrics = raw_turn_metrics if isinstance(raw_turn_metrics, dict) else {}
    return TurnCommitted(
        session_key=state.session_key,
        channel=msg.channel,
        chat_id=msg.chat_id,
        input_message=msg.content,
        persisted_user_message=None if omit_user_turn else msg.content,
        assistant_response=snap.ctx.reply,
        tools_used=list(snap.ctx.tools_used),
        thinking=snap.ctx.thinking,
        raw_reply=snap.ctx.response_metadata.raw_text,
        meme_tag=snap.ctx.meme_tag,
        meme_media_count=len(snap.ctx.media),
        tool_chain_raw=copy.deepcopy(tool_chain_list),
        tool_call_groups=to_tool_call_groups(tool_chain_list),
        timestamp=msg.timestamp,
        post_reply_budget=dict(budget),
        react_stats=dict(react_stats),
        extra={
            **_memory_extra(state),
            **({"source": source} if source else {}),
            **(
                {"committed_message_ids": list(state.committed_message_ids)}
                if state.committed_message_ids
                else {}
            ),
        },
        role_id=role_id,
        request_id=str((msg.metadata or {}).get("request_id") or "").strip(),
        thread_id=str((msg.metadata or {}).get("thread_id") or "").strip(),
        external_message_id=str(
            (msg.metadata or {}).get("external_message_id") or ""
        ).strip(),
        total_tokens=(
            value
            if isinstance((value := turn_metrics.get("total_tokens")), int)
            and value >= 0
            else None
        ),
        thinking_duration_ms=(
            value
            if isinstance((value := turn_metrics.get("thinking_duration_ms")), int)
            and value >= 0
            else None
        ),
    )


def _turn_finished(snap: TurnSnapshot) -> TurnFinished:
    """The ``TurnFinished`` event of the closed turn."""
    return TurnFinished(
        session_key=snap.state.session_key,
        channel=snap.outbound.channel,
        chat_id=snap.outbound.chat_id,
        reply=snap.outbound.content,
        tools_used=snap.ctx.tools_used,
        thinking=snap.ctx.thinking,
        will_dispatch=will_dispatch_outbound(snap),
    )


async def _dispatch(outbound_port: OutboundPort, snap: TurnSnapshot) -> None:
    """Hands the reply to the outbound port unless it is not to be dispatched."""
    outbound = snap.outbound
    if will_dispatch_outbound(snap):
        _ = await outbound_port.dispatch(
            OutboundDispatch(
                channel=outbound.channel,
                chat_id=outbound.chat_id,
                content=outbound.content,
                thinking=outbound.thinking,
                metadata=outbound.metadata,
                media=outbound.media,
                committed_message_id=outbound.committed_message_id,
            )
        )
