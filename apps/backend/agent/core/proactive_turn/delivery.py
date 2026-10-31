"""主动回复的单次投递与本轮目标解析。"""

from __future__ import annotations

import asyncio
import inspect
import logging
from typing import Any, Callable, Protocol

from agent.turns.result import TurnResult
from proactive_v2.context import AgentTickContext
from shiori_sdk.accounts.targets import AccountTarget
from shiori_sdk.core.conversation import InitiatedReply
from shiori_sdk.core.proactive_host import ProactiveHost

from .types import ResolveResult

logger = logging.getLogger(__name__)


class ProactiveDeliveryHost(Protocol):
    """发送阶段访问 pipeline 状态所需的最小宿主契约。"""

    _session_key: str
    _host: ProactiveHost

    def _record_tick_log_finish(
        self,
        ctx: AgentTickContext,
        *,
        gate_exit: str | None = None,
        result: TurnResult | None = None,
    ) -> None: ...


async def deliver_execute(
    pipeline: ProactiveDeliveryHost,
    ctx: AgentTickContext,
    decision: ResolveResult,
) -> float | None:
    """记录裁定，并把主动消息投递到本轮 gate 阶段选定的唯一目标。

    每条主动消息只投递一次。跳过不调用端口。成功和失败的副作用在端口返回之后
    执行，因此晚于 ``InitiatedMessageCommitted``。发送前的副作用仍在调用之前。
    """

    pipeline._record_tick_log_finish(ctx, result=decision.result)
    if not ctx.target_channel or not ctx.target_chat_id:
        raise RuntimeError("proactive target transport unavailable at delivery time")
    result = decision.result
    if result.decision == "skip":
        await _run_effects(result.side_effects)
        return 0.0
    await _run_effects(result.side_effects)
    reply = _initiated_reply(pipeline, ctx, result)
    host = pipeline._host
    try:
        if host.natural_reply_active():
            # ``deliver`` would open a second scope and drop the tick's plan.
            delivery = await host.commit_natural_reply(reply)
        else:
            delivery = await host.deliver(reply)
    except (Exception, asyncio.CancelledError):
        await _run_effects(result.failure_side_effects)
        raise
    await _run_effects(
        result.success_side_effects
        if delivery.complete
        else result.failure_side_effects
    )
    # A completed sequence can swallow a cancel that arrived during its last
    # send so these effects still run. Propagate it once they have.
    task = asyncio.current_task()
    if task is not None and task.cancelling():
        raise asyncio.CancelledError
    return 0.0


def _initiated_reply(
    pipeline: ProactiveDeliveryHost, ctx: AgentTickContext, result: TurnResult
) -> InitiatedReply:
    role_reply = result.role_reply
    context = result.reply_context
    outbound = result.outbound
    if role_reply is None or context is None or outbound is None:
        raise ValueError("proactive reply requires validated role state and outbound")
    extra = (
        result.trace.extra
        if result.trace is not None and isinstance(result.trace.extra, dict)
        else {}
    )
    account = extra.get("account_target")
    account_channel = ""
    account_target = None
    # The open plan was already retargeted when the draft was accepted.
    if (
        isinstance(account, dict)
        and account
        and not pipeline._host.natural_reply_active()
    ):
        account_channel = str(account.get("account_channel") or "")
        account_target = AccountTarget.from_arguments(account)
    return InitiatedReply(
        session_key=pipeline._session_key,
        content=role_reply.content,
        source="proactive",
        channel=ctx.target_channel,
        chat_id=ctx.target_chat_id,
        mood=role_reply.mood,
        thought=role_reply.thought,
        expected_mood_updated_at=context.previous_updated_at,
        moods=tuple(context.moods),
        media=tuple(outbound.media or []),
        account_channel=account_channel,
        account_target=account_target,
    )


async def _run_effects(effects: list[Any] | None) -> None:
    for effect in effects or []:
        try:
            maybe = effect.run()
            if inspect.isawaitable(maybe):
                await maybe
        except Exception as exc:
            logger.warning("turn side effect failed: %s", exc)


def resolve_target_transport(
    target_transport_fn: Callable[[], tuple[str, str] | None] | None,
) -> tuple[str, str] | None:
    """解析本轮唯一的目标渠道；``None`` 表示角色当前没有候选会话。

    tick 的 gate 阶段与 drift 发消息共用这一处解析。解析器抛出的配置/绑定错误
    直接冒泡，由 ProactiveLoop 的 tick 边界记录并继续下一轮。
    """

    if target_transport_fn is None:
        return None
    target = target_transport_fn()
    if target is None:
        return None
    channel, chat_id = (str(part).strip() for part in target)
    if not channel or not chat_id:
        raise ValueError(f"proactive target transport is incomplete: {target!r}")
    return channel, chat_id
