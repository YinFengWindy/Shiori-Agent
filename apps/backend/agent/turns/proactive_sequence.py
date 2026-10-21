"""One proactive role reply's private plan and receipt-backed message commits."""

from __future__ import annotations

import asyncio
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass, field, replace
from typing import TYPE_CHECKING, Any

from agent.account_delivery.service import AccountDelivery, ResolvedAccountTarget
from agent.turns.channel_sequence import BackgroundReply, channel_sequence_context
from agent.turns.outbound import OutboundDispatch, OutboundPort
from agent.turns.reply_interruption import (
    interruptible_reply_delivery,
    reply_was_invalidated,
)
from agent.turns import reply_sequence as pacing
from agent.turns.reply_sequence import ReplySequence
from core.common.cancellation import finish_started
from core.roles.turn_gate import wait_outside_role_gate
from bus.event_bus import EventBus
from bus.events_lifecycle import ReplyMessageCommitted
from session.manager import Session, SessionManager
from session.manager.models import build_session_message
from shiori_sdk.accounts.targets import UncertainDeliveryError
from shiori_sdk.messages import InboundMessage

if TYPE_CHECKING:
    from agent.core.passive_turn.natural_reply import NaturalReplyProtocol
    from agent.core.passive_turn.reply_recovery import CompletedReply


@dataclass
class ProactiveReplyPlan:
    """A model-authored reply bound to its current real destination and account."""

    protocol: NaturalReplyProtocol
    registration: BackgroundReply
    account_target: ResolvedAccountTarget | None = None
    completion: CompletedReply | None = None
    tool_chain: list[dict[str, Any]] = field(default_factory=list)
    committed_tool_count: int = 0

    @property
    def origin(self) -> InboundMessage:
        """Canonical destination; a retargeted draft replaces the initial candidate."""
        return self.registration.origin


_CURRENT: ContextVar[ProactiveReplyPlan | None] = ContextVar(
    "proactive_reply_plan", default=None
)


def current_proactive_reply() -> ProactiveReplyPlan | None:
    """Return the active tick's natural reply, absent when the role opts out."""
    return _CURRENT.get()


def record_proactive_tool_fact(
    *, call_id: str, name: str, arguments: dict, result: str
) -> None:
    """Retain completed work on this plan; draft/finish controls are not work facts."""
    plan = current_proactive_reply()
    if plan is None or name in {"message_push", "finish_turn", "finish_drift"}:
        return
    plan.tool_chain.append(
        {
            "text": "",
            "calls": [
                {
                    "call_id": call_id,
                    "name": name,
                    "arguments": arguments,
                    "result": result,
                }
            ],
        }
    )


@contextmanager
def proactive_reply_scope(plan: ProactiveReplyPlan):
    """Make the same plan available to proactive draft and drift delivery owners."""
    token = _CURRENT.set(plan)
    try:
        yield
    finally:
        _CURRENT.reset(token)


async def commit_proactive_sequence(
    *,
    plan: ProactiveReplyPlan,
    sequence: ReplySequence,
    template: dict[str, Any],
    manager: SessionManager,
    session: Session,
    outbound: OutboundPort,
    account_delivery: AccountDelivery | None,
    event_bus: EventBus | None,
    state_kwargs: dict[str, Any],
    delivered: list[dict[str, Any]],
) -> None:
    """Finish each started send and record before allowing its suffix to stop.

    Failed/uncertain attempts remain delivery records. Only confirmed rows enter
    conversation history, and only a complete plan may publish its role state.
    """
    context = channel_sequence_context()
    if context is None:
        raise RuntimeError("主动自然回复缺少运行时投递所有者")
    origin = plan.origin

    async def publish(index: int, content: str) -> None:
        metadata = {
            **template["metadata"],
            **origin.metadata,
            "reply_sequence_id": str(origin.metadata["turn_id"]),
            "reply_sequence_index": index,
        }
        message = build_session_message(
            "assistant",
            content,
            **{
                key: value
                for key, value in template.items()
                if key
                not in {"id", "role", "content", "metadata", "timestamp", "media"}
            },
            media=template.get("media") if index == 0 else None,
            metadata=metadata,
        )
        if index == 0 and plan.completion is not None:
            thinking = plan.completion.response.thinking
            if thinking is not None:
                message["reasoning_content"] = thinking
        resolved = plan.account_target
        if resolved is not None:
            if account_delivery is None:
                raise RuntimeError("账号目标发送服务不可用")
            message["delivery_status"] = "pending"
            await manager.append_messages(session, [message], pending_messages=True)
            try:
                # Native account transports own request deadlines and uncertainty.
                receipt = await account_delivery.send(
                    resolved.channel,
                    resolved.role_id,
                    (
                        resolved.target
                        if index == 0
                        else replace(resolved.target, mention_ids=())
                    ),
                    content,
                    media=message.get("media"),
                    source="proactive",
                    expected_access=resolved.access,
                )
            except (TimeoutError, ConnectionError, OSError, UncertainDeliveryError):
                manager.mark_message_delivery(
                    session.key,
                    message_id=str(message["id"]),
                    thread_id=str(metadata["thread_id"]),
                    delivery_status="uncertain",
                )
                raise
            except Exception:
                manager.mark_message_delivery(
                    session.key,
                    message_id=str(message["id"]),
                    thread_id=str(metadata["thread_id"]),
                    delivery_status="failed",
                )
                raise
            message["metadata"].update(receipt.message_metadata())
            manager.mark_message_delivery(
                session.key,
                message_id=str(message["id"]),
                thread_id=str(metadata["thread_id"]),
                delivery_status="sent",
                external_message_id=receipt.platform_message_id,
                metadata_updates=receipt.message_metadata(),
            )
        else:
            receipt = await outbound.dispatch(
                OutboundDispatch(
                    channel=origin.channel,
                    chat_id=origin.chat_id,
                    content=content,
                    media=list(message.get("media") or []),
                    metadata={**metadata, "pending_commit": True},
                )
            )
            if receipt is None:
                raise RuntimeError("桌面主动回复未被接纳")
            await manager.append_messages(session, [message], pending_messages=True)
        delivered.append(message)
        if index == len(sequence.messages) - 1:
            current = manager.get_or_create(session.key)
            # A different chat may finish while this plan yields its pacing wait.
            if str(
                current.metadata.get("current_mood_updated_at", "")
            ) == state_kwargs.get("expected_mood_updated_at"):
                await manager.append_messages(current, [], **state_kwargs)
        if event_bus is not None:
            await event_bus.emit(
                ReplyMessageCommitted(
                    session_key=session.key,
                    turn_id=str(metadata["turn_id"]),
                    message_ids=(str(message["id"]),),
                )
            )

    with context.owner.delivering(), interruptible_reply_delivery():
        for index, content in enumerate(sequence.messages):
            if index:
                await wait_outside_role_gate(
                    lambda: pacing.wait_between_messages(
                        pacing.message_pause(sequence.messages[index - 1])
                    )
                )
            if reply_was_invalidated():
                raise asyncio.CancelledError
            await finish_started(publish(index, content))
