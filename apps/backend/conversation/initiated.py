"""Commit one ``InitiatedReply`` through the turn orchestrator.

Both doors (``CONVERSATION`` for a generation, ``PROACTIVE_HOST.deliver`` for
the published generation) call ``commit_initiated_reply``. The orchestrator
still owns validation, the send, the committed event and the stored ids.
"""

from __future__ import annotations

import asyncio
from contextlib import contextmanager
from typing import Any, Iterator
from uuid import uuid4

from agent.core.passive_turn.natural_reply import NaturalReply
from agent.turns.orchestrator import TurnOrchestrator
from agent.turns.proactive_sequence import (
    current_proactive_reply,
    record_proactive_tool_fact,
)
from agent.turns.reply_interruption import ReplyInterruption
from agent.turns.reply_sequence import ReplySequence
from agent.turns.result import TurnOutbound, TurnResult, TurnTrace
from core.roles.affection_access import (
    AffectionGetter,
    bind_turn_affection,
    reset_turn_affection,
)
from core.roles.reply_policy import (
    ReplyPolicyGetter,
    bind_turn_reply_policy,
    reset_turn_reply_policy,
)
from core.common.cancellation import finish_started
from core.roles.reply_state import RoleReplyContext, validate_role_reply
from shiori_sdk.accounts.targets import AccountTarget
from shiori_sdk.core.conversation import InitiatedDelivery, InitiatedReply


@contextmanager
def bound_turn_getters(
    affection: AffectionGetter | None,
    reply_policy: ReplyPolicyGetter | None,
) -> Iterator[None]:
    """Bind the generation's affection and reply-policy getters for one delivery."""
    affection_token = bind_turn_affection(affection)
    policy_token = bind_turn_reply_policy(reply_policy)
    try:
        yield
    finally:
        reset_turn_reply_policy(policy_token)
        reset_turn_affection(affection_token)


def account_target_mapping(
    account_channel: str, target: AccountTarget
) -> dict[str, Any]:
    """The orchestrator's account-target dict for one initiated reply."""
    return {"account_channel": account_channel, **target.to_payload()}


async def commit_initiated_reply(
    orchestrator: TurnOrchestrator, reply: InitiatedReply
) -> InitiatedDelivery:
    """Send ``reply``, store what was sent, and report the stored message ids.

    The orchestrator reports the ids itself. See
    ``Conversation.deliver_initiated_reply`` for what raises, what an
    incomplete result means and what a failed send leaves behind. A natural
    sequence needs natural chat and either a runtime lease or an already
    bound channel-sequence owner.
    """
    _reject_ill_shaped(orchestrator, reply)
    committed: list[str] = []
    if not reply.messages:
        sent = await orchestrator.handle_proactive_turn(
            result=_turn_result(reply, include_target=True),
            session_key=reply.session_key,
            channel=reply.channel,
            chat_id=reply.chat_id,
            source=reply.source,
            committed=committed,
        )
        return InitiatedDelivery(message_ids=tuple(committed), complete=sent)
    interruption = ReplyInterruption()
    task = asyncio.create_task(
        _send_sequence(orchestrator, reply, interruption, committed),
        name=f"initiated-reply:{reply.session_key}",
    )
    try:
        await finish_started(task, on_cancel=interruption.invalidate)
    except asyncio.CancelledError:
        current = asyncio.current_task()
        if current is not None and current.cancelling():
            raise
        # A newer user message stopped the sequence; its sent prefix stays.
        return InitiatedDelivery(message_ids=tuple(committed), complete=False)
    return InitiatedDelivery(message_ids=tuple(committed), complete=True)


def _reject_ill_shaped(orchestrator: TurnOrchestrator, reply: InitiatedReply) -> None:
    if reply.tool_facts and not reply.messages:
        raise ValueError("工具事实只能随自然回复序列保存")
    if not reply.messages:
        return
    if reply.content != "\n\n".join(reply.messages):
        raise ValueError("主动草稿与已校验消息列表不一致")
    if not orchestrator.natural_chat_enabled(reply.session_key):
        raise RuntimeError("自然回复序列需要角色开启自然聊天")


async def _send_sequence(
    orchestrator: TurnOrchestrator,
    reply: InitiatedReply,
    interruption: ReplyInterruption,
    committed: list[str],
) -> None:
    async with orchestrator.natural_reply_scope(
        reply.session_key,
        reply.channel,
        reply.chat_id,
        turn_id=f"initiated:{uuid4().hex}",
        interruption=interruption,
    ):
        plan = current_proactive_reply()
        if plan is None:
            raise RuntimeError("自然回复序列需要角色开启自然聊天")
        plan.protocol.reply = NaturalReply(
            sequence=ReplySequence(tuple(reply.messages)),
            raw_text="",
        )
        for fact in reply.tool_facts:
            record_proactive_tool_fact(
                call_id=fact.call_id,
                name=fact.name,
                arguments=dict(fact.arguments),
                result=fact.result,
            )
        if reply.account_target is not None:
            await orchestrator.retarget_natural_reply(
                reply.session_key,
                account_target_mapping(reply.account_channel, reply.account_target),
            )
        await orchestrator.handle_proactive_turn(
            result=_turn_result(reply, include_target=False),
            session_key=reply.session_key,
            channel=reply.channel,
            chat_id=reply.chat_id,
            source=reply.source,
            committed=committed,
        )


def _turn_result(reply: InitiatedReply, *, include_target: bool) -> TurnResult:
    # The caller's tick-start state: the orchestrator rejects the reply when
    # the stored mood moved on after it (``expected_mood_updated_at``).
    context = RoleReplyContext(
        moods=reply.moods, previous_updated_at=reply.expected_mood_updated_at
    )
    role_reply = validate_role_reply(
        {"content": reply.content, "mood": reply.mood, "thought": reply.thought},
        context.moods,
        allow_empty_content=bool(reply.media),
    )
    extra: dict[str, Any] = {}
    if include_target and reply.account_target is not None:
        extra["account_target"] = account_target_mapping(
            reply.account_channel, reply.account_target
        )
    return TurnResult(
        decision="reply",
        role_reply=role_reply,
        reply_context=context,
        outbound=TurnOutbound(
            session_key=reply.session_key,
            content=role_reply.content,
            media=list(reply.media),
        ),
        trace=TurnTrace(source="proactive", extra=extra),
    )
