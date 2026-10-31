"""Commit one ``InitiatedReply`` through the turn orchestrator.

Both doors (``CONVERSATION`` for a generation, ``PROACTIVE_HOST.deliver`` for
the published generation) call ``commit_initiated_reply``. The orchestrator
still owns validation, the send and the committed event.
"""

from __future__ import annotations

from contextlib import contextmanager
from typing import Any, Iterator
from uuid import uuid4

from agent.core.passive_turn.natural_reply import NaturalReply
from agent.turns.orchestrator import TurnOrchestrator
from agent.turns.proactive_sequence import (
    current_proactive_reply,
    record_proactive_tool_fact,
)
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
from core.roles.reply_state import validate_role_reply
from shiori_sdk.core.conversation import (
    InitiatedAccountTarget,
    InitiatedMessageCommitted,
    InitiatedReply,
)


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


def account_target_mapping(target: InitiatedAccountTarget) -> dict[str, Any]:
    """The orchestrator's account-target dict for one initiated reply."""
    payload: dict[str, Any] = {
        "account_channel": target.account_channel,
        "target_kind": target.target_kind,
        "target_id": target.target_id,
        "group_id": target.group_id,
        "mention_ids": list(target.mention_ids),
    }
    if target.message_thread_id is not None:
        payload["message_thread_id"] = target.message_thread_id
    return payload


async def commit_initiated_reply(
    orchestrator: TurnOrchestrator, reply: InitiatedReply
) -> str:
    """Store ``reply`` and return the last committed message id.

    ``""`` when the send was refused and nothing was stored. Validation, a
    missing role, a disallowed target and a failed send raise, and a failed
    send stores nothing. A natural sequence needs natural chat and either a
    runtime lease or an already bound channel-sequence owner.
    """
    _reject_ill_shaped(orchestrator, reply)
    captured: list[InitiatedMessageCommitted] = []

    def observe(event: InitiatedMessageCommitted) -> None:
        if event.session_key == reply.session_key and event.source == reply.source:
            captured.append(event)

    bus = orchestrator._event_bus
    if bus is not None:
        bus.on(InitiatedMessageCommitted, observe)
    try:
        sent = await _send(orchestrator, reply)
    finally:
        if bus is not None:
            bus.off(InitiatedMessageCommitted, observe)
    if not sent or not captured:
        return ""
    return captured[-1].message_id


def _reject_ill_shaped(orchestrator: TurnOrchestrator, reply: InitiatedReply) -> None:
    if reply.tool_facts and not reply.messages:
        raise ValueError("工具事实只能随自然回复序列保存")
    if not reply.messages:
        return
    if reply.content != "\n\n".join(reply.messages):
        raise ValueError("主动草稿与已校验消息列表不一致")
    if not orchestrator.natural_chat_enabled(reply.session_key):
        raise RuntimeError("自然回复序列需要角色开启自然聊天")


async def _send(orchestrator: TurnOrchestrator, reply: InitiatedReply) -> bool:
    if not reply.messages:
        return await orchestrator.handle_proactive_turn(
            result=_turn_result(orchestrator, reply, include_target=True),
            session_key=reply.session_key,
            channel=reply.channel,
            chat_id=reply.chat_id,
            source=reply.source,
        )
    turn_id = f"initiated:{uuid4().hex}"
    async with orchestrator.natural_reply_scope(
        reply.session_key,
        reply.channel,
        reply.chat_id,
        turn_id=turn_id,
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
                reply.session_key, account_target_mapping(reply.account_target)
            )
        return await orchestrator.handle_proactive_turn(
            result=_turn_result(orchestrator, reply, include_target=False),
            session_key=reply.session_key,
            channel=reply.channel,
            chat_id=reply.chat_id,
            source=reply.source,
        )


def _turn_result(
    orchestrator: TurnOrchestrator,
    reply: InitiatedReply,
    *,
    include_target: bool,
) -> TurnResult:
    context = orchestrator.capture_reply_context(reply.session_key)
    role_reply = validate_role_reply(
        {"content": reply.content, "mood": reply.mood, "thought": reply.thought},
        context.moods,
        allow_empty_content=bool(reply.media),
    )
    extra: dict[str, Any] = {}
    if include_target and reply.account_target is not None:
        extra["account_target"] = account_target_mapping(reply.account_target)
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
