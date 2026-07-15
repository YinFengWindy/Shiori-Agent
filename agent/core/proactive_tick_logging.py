"""主动回复 tick 生命周期与工具步骤日志。"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from agent.turns.result import TurnResult
from proactive_v2.context import AgentTickContext


def record_tick_log_start(
    *,
    state_store: Any,
    session_key: str,
    ctx: AgentTickContext,
) -> None:
    """记录一次主动 tick 的起点。"""

    state_store.record_tick_log_start(
        tick_id=ctx.tick_id,
        session_key=session_key,
        started_at=ctx.now_utc.isoformat(),
        gate_exit=None,
    )


def record_tick_log_finish(
    *,
    state_store: Any,
    session_key: str,
    ctx: AgentTickContext,
    gate_exit: str | None = None,
    result: TurnResult | None = None,
) -> None:
    """记录主动 tick 的最终裁定与上下文快照。"""

    decision = result.decision if result is not None else ctx.terminal_action
    if ctx.drift_entered and result is None and decision is None:
        decision = "reply" if ctx.drift_message_sent else "skip"
    trace_extra = result.trace.extra if result is not None and result.trace is not None else {}
    skip_reason = str(trace_extra.get("skip_reason") or ctx.skip_reason or "")
    final_message = ""
    if result is not None and result.outbound is not None:
        final_message = str(result.outbound.content or "")
    elif ctx.final_message:
        final_message = ctx.final_message
    state_store.record_tick_log_finish(
        tick_id=ctx.tick_id,
        session_key=session_key,
        started_at=ctx.now_utc.isoformat(),
        finished_at=datetime.now(timezone.utc).isoformat(),
        gate_exit=gate_exit,
        terminal_action=decision,
        skip_reason=skip_reason,
        steps_taken=ctx.steps_taken,
        alert_count=len(ctx.fetched_alerts),
        content_count=len(ctx.fetched_contents),
        context_count=len(ctx.fetched_context),
        interesting_ids=sorted(ctx.interesting_item_ids),
        discarded_ids=sorted(ctx.discarded_item_ids),
        cited_ids=list(ctx.cited_item_ids),
        drift_entered=ctx.drift_entered,
        final_message=final_message,
    )


def record_tick_step(
    *,
    state_store: Any,
    ctx: AgentTickContext,
    phase: str,
    tool_name: str,
    tool_call_id: str,
    tool_args: dict[str, Any],
    tool_result_text: str,
) -> None:
    """记录一次主动工具调用后的完整决策状态。"""

    state_store.record_tick_step_log(
        tick_id=ctx.tick_id,
        step_index=ctx.steps_taken,
        phase=phase,
        tool_name=tool_name,
        tool_call_id=tool_call_id,
        tool_args=tool_args,
        tool_result_text=tool_result_text,
        terminal_action_after=ctx.terminal_action,
        skip_reason_after=ctx.skip_reason,
        interesting_ids_after=sorted(ctx.interesting_item_ids),
        discarded_ids_after=sorted(ctx.discarded_item_ids),
        cited_ids_after=list(ctx.cited_item_ids),
        final_message_after=ctx.final_message,
    )
