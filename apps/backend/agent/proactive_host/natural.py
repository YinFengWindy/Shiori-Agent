"""The natural reply a proactive tick opens through ``PROACTIVE_HOST``.

One tick has at most one plan: the scope binds it, ``execute_tool`` records
work facts on it, ``complete(natural_draft=True)`` turns the model's draft
into its validated message list, and ``deliver`` sends that list through it.
"""

from __future__ import annotations

from collections.abc import AsyncIterator, Mapping
from contextlib import asynccontextmanager
from contextvars import ContextVar
from dataclasses import replace

from agent.core.passive_turn.natural_reply import (
    InvalidNaturalReply,
    finish_reply_schema,
)
from agent.provider import LLMProvider, LLMResponse
from agent.turns.orchestrator import TurnOrchestrator
from agent.turns.proactive_sequence import (
    current_proactive_reply,
    record_proactive_tool_fact,
)
from agent.turns.reply_interruption import ReplyInterruption, ReplyPlanInvalidated
from conversation.initiated import initiated_turn_result, report_delivery
from prompts.natural_chat import FINISH_REPLY_TOOL_NAME
from shiori_sdk.core.conversation import InitiatedDelivery, InitiatedReply
from shiori_sdk.core.proactive_host import NaturalReplyInvalidated


class HostReplyTicket:
    """The ticket ``begin_natural_reply`` issues. Other objects are refused.

    While its scope is open it also remembers the session and the chat the
    plan was opened on or last moved to, the only address ``deliver`` sends to.
    """

    def __init__(self) -> None:
        self.interruption = ReplyInterruption()
        self.session_key = ""
        self.channel = ""
        self.chat_id = ""

    def invalidate(self) -> None:
        self.interruption.invalidate()


_SCOPE: ContextVar[HostReplyTicket | None] = ContextVar(
    "proactive_natural_scope", default=None
)


@asynccontextmanager
async def natural_reply_scope(
    orchestrator: TurnOrchestrator,
    ticket: HostReplyTicket,
    session_key: str,
    channel: str,
    chat_id: str,
    *,
    turn_id: str,
) -> AsyncIterator[None]:
    """Bind ``ticket``'s plan and commit its tool facts before the plan ends.

    Facts are committed while the plan is still current, including when the
    body raises ``NaturalReplyInvalidated``.
    """
    ticket.session_key, ticket.channel, ticket.chat_id = session_key, channel, chat_id
    token = _SCOPE.set(ticket)
    try:
        async with orchestrator.natural_reply_scope(
            session_key,
            channel,
            chat_id,
            turn_id=turn_id,
            interruption=ticket.interruption,
        ):
            try:
                yield
            except ReplyPlanInvalidated as exc:
                raise NaturalReplyInvalidated(str(exc)) from exc
            finally:
                await orchestrator.commit_proactive_tool_facts(session_key)
    finally:
        _SCOPE.reset(token)


async def retarget_transport(
    orchestrator: TurnOrchestrator, session_key: str, channel: str, chat_id: str
) -> None:
    """Point the open plan at another candidate chat and remember it."""
    await orchestrator.retarget_natural_transport(session_key, channel, chat_id)
    ticket = _SCOPE.get()
    if ticket is not None:
        ticket.channel, ticket.chat_id = channel, chat_id


async def deliver_through_plan(
    orchestrator: TurnOrchestrator, reply: InitiatedReply
) -> InitiatedDelivery:
    """Send the tick's draft through the plan open on this task.

    Refuses, before writing, a reply for another session or chat, or one that
    carries its own messages, tool facts or account target. The delivery runs
    on the tick's task, so an interruption stops the tick (see
    ``report_delivery``).
    """
    ticket = _SCOPE.get()
    plan = current_proactive_reply()
    if ticket is None or plan is None:
        raise RuntimeError("自然回复投递需要已打开的回复计划")
    if reply.messages or reply.tool_facts or reply.account_target is not None:
        raise ValueError("自然回复计划内只投递本轮草稿，消息、工具事实和改投由计划持有")
    if (reply.session_key, reply.channel, reply.chat_id) != (
        ticket.session_key,
        ticket.channel,
        ticket.chat_id,
    ):
        raise ValueError(
            "主动回复的会话或目标不属于当前自然回复计划: "
            f"{reply.session_key} {reply.channel}:{reply.chat_id}"
        )
    accepted = plan.protocol.reply
    if accepted is None:
        raise ValueError("主动自然回复尚未通过消息列表校验")
    committed: list[str] = []
    return await report_delivery(
        orchestrator.handle_proactive_turn(
            result=initiated_turn_result(reply, include_target=False),
            session_key=reply.session_key,
            channel=reply.channel,
            chat_id=reply.chat_id,
            source=reply.source,
            committed=committed,
        ),
        committed,
        total=len(accepted.sequence.messages),
        stops_caller=True,
    )


def record_tool_fact(
    call_id: str, name: str, arguments: Mapping[str, object], result: str
) -> None:
    """Record one finished tool call on the open plan; no plan does nothing."""
    record_proactive_tool_fact(
        call_id=call_id, name=name, arguments=dict(arguments), result=result
    )


def natural_reply_properties() -> Mapping[str, object]:
    """The ``messages`` property a natural draft carries instead of its text."""
    return finish_reply_schema()["function"]["parameters"]["properties"]


def natural_reply_messages() -> tuple[str, ...] | None:
    """The messages the open plan accepted, or None before a draft is accepted."""
    plan = current_proactive_reply()
    if plan is None:
        raise RuntimeError("自然回复消息列表需要已打开的回复计划")
    reply = plan.protocol.reply
    return None if reply is None else tuple(reply.sequence.messages)


async def complete_natural_draft(
    response: LLMResponse,
    *,
    messages: list[dict],
    provider: LLMProvider,
    model: str,
    max_tokens: int,
) -> LLMResponse:
    """Turn a proactive draft into the open plan's validated message list.

    Evidence, destination and role state remain the original draft's fields.
    A format correction only exposes finish_reply and cannot replay work or
    choose a different destination. Business tool calls the model made
    instead pass through unchanged.
    """
    plan = current_proactive_reply()
    if plan is None:
        raise RuntimeError("自然回复补全需要已打开的回复计划")
    drafts = [call for call in response.tool_calls if call.name == "message_push"]
    if not drafts:
        if response.tool_calls:
            # Validate deferred parsing failures on actual business calls.
            if plan.protocol.pending_work(response):
                return response
            raise InvalidNaturalReply("主动回复需要保留 message_push 的目标和证据参数")
        raise InvalidNaturalReply("主动自然回复缺少决策工具调用")
    adapted = replace(
        response,
        tool_calls=[
            (
                replace(
                    call,
                    name=FINISH_REPLY_TOOL_NAME,
                    arguments={"messages": call.arguments.get("messages")},
                )
                if call.name == "message_push"
                else call
            )
            for call in response.tool_calls
        ],
    )
    if plan.protocol.pending_work(adapted):
        return adapted
    if len(drafts) != 1 or drafts[0].arguments_error:
        # An ambiguous/malformed envelope cannot safely retain target/evidence.
        raise InvalidNaturalReply("主动自然回复需要一个参数完整的 message_push 草稿")
    plan.completion = await plan.protocol.complete(
        adapted,
        messages=messages,
        provider=provider,
        model=model,
        max_tokens=max_tokens,
    )
    reply = plan.protocol.reply
    assert reply is not None
    return replace(
        plan.completion.response,
        tool_calls=[
            replace(
                drafts[0],
                arguments={
                    **drafts[0].arguments,
                    "messages": list(reply.sequence.messages),
                },
            )
        ],
    )
