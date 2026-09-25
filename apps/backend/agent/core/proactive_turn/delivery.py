"""主动回复的单次投递与本轮目标解析。"""

from __future__ import annotations

from typing import Any, Callable, Protocol

from agent.turns.result import TurnResult
from proactive_v2.context import AgentTickContext

from .types import ResolveResult


class ProactiveDeliveryHost(Protocol):
    """发送阶段访问 pipeline 状态所需的最小宿主契约。"""

    _session_key: str
    _turn_orchestrator: Any
    _target_transport_fn: Callable[[], tuple[str, str] | None] | None

    def _record_tick_log_finish(
        self,
        ctx: AgentTickContext,
        *,
        gate_exit: str | None = None,
        gate_name: str = "",
        gate_reason: str = "",
        gate_metadata: dict[str, object] | None = None,
        result: TurnResult | None = None,
    ) -> None: ...


async def deliver_execute(
    pipeline: ProactiveDeliveryHost,
    ctx: AgentTickContext,
    decision: ResolveResult,
) -> float | None:
    """记录裁定，并把主动消息投递到本轮 gate 阶段选定的唯一目标。

    每条主动消息只投递一次，不再换渠道重发。
    """

    pipeline._record_tick_log_finish(ctx, result=decision.result)
    if pipeline._turn_orchestrator is None:
        raise RuntimeError("proactive turn_orchestrator is required")
    if not ctx.target_channel or not ctx.target_chat_id:
        raise RuntimeError("proactive target transport unavailable at delivery time")
    await pipeline._turn_orchestrator.handle_proactive_turn(
        result=decision.result,
        session_key=pipeline._session_key,
        channel=ctx.target_channel,
        chat_id=ctx.target_chat_id,
    )
    return 0.0


def resolve_target_transport(
    pipeline: ProactiveDeliveryHost,
) -> tuple[str, str] | None:
    """解析本轮唯一的目标渠道；``None`` 表示角色当前没有候选会话。

    解析器抛出的配置/绑定错误直接冒泡，由 ProactiveLoop 的 tick 边界记录并继续下一轮。
    """

    if pipeline._target_transport_fn is None:
        return None
    target = pipeline._target_transport_fn()
    if target is None:
        return None
    channel, chat_id = (str(part).strip() for part in target)
    if not channel or not chat_id:
        raise ValueError(f"proactive target transport is incomplete: {target!r}")
    return channel, chat_id
