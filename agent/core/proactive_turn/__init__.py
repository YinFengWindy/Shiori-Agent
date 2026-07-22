"""主动回复链路的稳定 facade 与顶层 pipeline 编排。"""

from __future__ import annotations

import asyncio
import logging
import random as _random_module
import time
from datetime import datetime, timezone
from typing import Any

from agent.tool_hooks import ToolExecutor
from agent.turns.result import TurnResult
from core.common.diagnostic_log import diagnostic_context, diagnostic_line
from proactive_v2.context import AgentTickContext
from proactive_v2.gateway import GatewayResult

from .delivery import (
    cancel_pending_retries as _cancel_pending_retries,
    deliver_execute as _deliver_execute,
    deliver_retries as _deliver_retries,
    has_user_replied_since as _has_user_replied_since,
    notify_user_reply as _notify_user_reply,
    resolve_target_transport as _resolve_target_transport,
    resolve_target_transports as _resolve_target_transports,
    wait_for_retry_or_user_reply as _wait_for_retry_or_user_reply,
)
from .judge import (
    append_tool_messages as _append_tool_messages,
    judge_evaluate as _judge_evaluate,
    run_tool_step as _run_tool_step,
)
from .phases import (
    fetch_pull as _fetch_pull,
    finalize_after_drift as _finalize_after_drift,
    gate_check as _gate_check,
)
from .prompt_context import (
    allow_relationship_only_fallback as _allow_relationship_only_fallback,
    build_runtime_context_message as _build_runtime_context_message,
    build_system_prompt as _build_system_prompt,
    is_relationship_only_fallback as _is_relationship_only_fallback,
    read_workspace_context_for_prompt as _read_workspace_context_for_prompt,
    relationship_fallback_style_hint as _relationship_fallback_style_hint,
    render_alert_block as _render_alert_block,
    render_content_block as _render_content_block,
    render_context_block as _render_context_block,
)
from .tick_logging import (
    record_tick_log_finish as _record_tick_log_finish,
    record_tick_log_start as _record_tick_log_start,
    record_tick_step as _record_tick_step,
)
from .resolution import (
    ack_discarded,
    ack_on_success,
    ack_post_guard_fail,
    build_delivery_key,
    resolve_decide as _resolve_decide,
)
from .types import (
    FeedResult,
    GateResult,
    ProactiveTurnPipelineDeps,
    ResolveResult,
)
from .gates import ProactiveGateChain

logger = logging.getLogger(__name__)

__all__ = [
    "FeedResult",
    "GateResult",
    "ProactiveTurnPipeline",
    "ProactiveTurnPipelineDeps",
    "ProactiveGateChain",
    "ResolveResult",
    "ack_discarded",
    "ack_on_success",
    "ack_post_guard_fail",
    "build_delivery_key",
]


class ProactiveTurnPipeline:
    """编排 Gate、Fetch、Judge、Resolve 和 Deliver 五段主动回复链路。"""

    def __init__(self, deps: ProactiveTurnPipelineDeps) -> None:
        self._cfg = deps.cfg
        self._session_key = deps.session_key
        self._state_store = deps.state_store
        self._any_action_gate = deps.any_action_gate
        self._last_user_at_fn = deps.last_user_at_fn
        self._passive_busy_fn = deps.passive_busy_fn
        self._turn_orchestrator = deps.turn_orchestrator
        self._deduper = deps.deduper
        self._tool_deps = deps.tool_deps
        self._gateway_deps = deps.gateway_deps
        self._workspace_context_fn = deps.workspace_context_fn
        self._llm_fn = deps.llm_fn
        self._rng = deps.rng if deps.rng is not None else _random_module.Random()
        self._recent_proactive_fn = deps.recent_proactive_fn
        self._drift_pipeline = deps.drift_pipeline
        self._target_transport_fn = deps.target_transport_fn
        self._target_transports_fn = deps.target_transports_fn
        self._retry_wait_fn = deps.retry_wait_fn
        self._proactive_gates = deps.proactive_gates or ProactiveGateChain()
        self._tool_executor = ToolExecutor(deps.tool_hooks or [])
        self._retry_task: asyncio.Task[None] | None = None
        self._retry_cancel_event = asyncio.Event()

        if (
            self._drift_pipeline is not None
            and getattr(self._drift_pipeline, "step_recorder", None) is None
        ):
            self._drift_pipeline.step_recorder = (
                lambda ctx, phase, tool_name, tool_call_id, tool_args, tool_result_text: (
                    self._record_tick_step(
                        ctx,
                        phase=phase,
                        tool_name=tool_name,
                        tool_call_id=tool_call_id,
                        tool_args=tool_args,
                        tool_result_text=tool_result_text,
                    )
                )
            )

        self.last_ctx: AgentTickContext | None = None
        self._last_gateway_result: GatewayResult | None = None

    async def run(self) -> float | None:
        """处理一次主动 tick，并返回本轮基础分值。"""

        started = time.perf_counter()
        ctx = AgentTickContext(
            session_key=self._session_key,
            now_utc=datetime.now(timezone.utc),
        )
        with diagnostic_context(
            session=self._session_key,
            flow="proactive",
            tick=ctx.tick_id,
        ):
            logger.info(
                diagnostic_line(
                    "ProactiveTurnPipeline.run",
                    event="start",
                    flow="proactive",
                    phase="pregate",
                    session=self._session_key,
                    tick=ctx.tick_id,
                    action="run",
                )
            )
            try:
                return await self._run_with_context(ctx, started)
            except Exception as exc:
                logger.exception(
                    diagnostic_line(
                        "ProactiveTurnPipeline.run",
                        event="phase_error",
                        flow="proactive",
                        phase="tick",
                        session=self._session_key,
                        tick=ctx.tick_id,
                        action="fail",
                        reason="proactive_tick_error",
                        duration_ms=int((time.perf_counter() - started) * 1000),
                        error_type=type(exc).__name__,
                        note=str(exc)[:160],
                    )
                )
                raise

    async def _run_with_context(
        self,
        ctx: AgentTickContext,
        started: float,
    ) -> float | None:
        gate = self._gate_check(ctx)
        if gate.blocked:
            logger.info(
                diagnostic_line(
                    "ProactiveTurnPipeline.run",
                    event="gate_exit",
                    flow="proactive",
                    phase="pregate",
                    session=self._session_key,
                    tick=ctx.tick_id,
                    action="skip",
                    reason=gate.reason,
                    duration_ms=int((time.perf_counter() - started) * 1000),
                )
            )
            self._record_tick_log_finish(ctx, gate_exit=gate.reason)
            return gate.base_score

        ctx.context_as_fallback_open = gate.context_as_fallback_open
        ctx.selected_gate = gate.activation
        self.last_ctx = ctx
        self._record_tick_log_start(ctx)
        logger.info(
            diagnostic_line(
                "ProactiveTurnPipeline.run",
                event="end",
                flow="proactive",
                phase="pregate",
                session=self._session_key,
                tick=ctx.tick_id,
                action="continue",
                duration_ms=int((time.perf_counter() - started) * 1000),
            )
        )

        with diagnostic_context(phase="gateway"):
            feed = await self._fetch_pull(ctx)
        if feed.drift_entered:
            self._finalize_after_drift(ctx)
            return feed.base_score

        if feed.messages and ctx.terminal_action is None:
            with diagnostic_context(phase="agent_loop"):
                await self._judge_evaluate(ctx, feed.messages)

        with diagnostic_context(phase="resolve"):
            decision = await self._resolve_decide(ctx)

        score = await self._deliver_execute(ctx, decision)
        logger.info(
            diagnostic_line(
                "ProactiveTurnPipeline.run",
                event="end",
                flow="proactive",
                phase="resolve",
                session=self._session_key,
                tick=ctx.tick_id,
                action=decision.action,
                reason=ctx.skip_reason or "-",
                duration_ms=int((time.perf_counter() - started) * 1000),
                counts=f"steps:{ctx.steps_taken},interesting:{len(ctx.interesting_item_ids)},discarded:{len(ctx.discarded_item_ids)}",
            )
        )
        ctx.content_store.clear()
        return score

    def _gate_check(self, ctx: AgentTickContext) -> GateResult:
        return _gate_check(self, ctx)

    async def _fetch_pull(self, ctx: AgentTickContext) -> FeedResult:
        return await _fetch_pull(self, ctx)

    async def _judge_evaluate(
        self,
        ctx: AgentTickContext,
        messages: list[dict],
    ) -> None:
        await _judge_evaluate(self, ctx, messages)

    async def _resolve_decide(self, ctx: AgentTickContext) -> ResolveResult:
        return await _resolve_decide(self, ctx)

    async def _deliver_execute(
        self,
        ctx: AgentTickContext,
        decision: ResolveResult,
    ) -> float | None:
        return await _deliver_execute(self, ctx, decision)

    async def _deliver_retries(
        self,
        *,
        transports: list[tuple[str, str]],
        result: TurnResult,
        sent_at: datetime,
    ) -> None:
        await _deliver_retries(
            self,
            transports=transports,
            result=result,
            sent_at=sent_at,
        )

    async def _wait_for_retry_or_user_reply(self, delay: float) -> bool:
        return await _wait_for_retry_or_user_reply(self, delay)

    def notify_user_reply(self) -> None:
        """取消当前 session 的多渠道后台重试。"""

        _notify_user_reply(self)

    async def cancel_pending_retries(self) -> None:
        """等待并清理当前 session 的多渠道后台重试任务。"""

        await _cancel_pending_retries(self)

    def _has_user_replied_since(self, sent_at: datetime) -> bool:
        return _has_user_replied_since(self, sent_at)

    def _resolve_target_transports(self) -> list[tuple[str, str]]:
        return _resolve_target_transports(self)

    def _resolve_target_transport(self) -> tuple[str, str] | None:
        return _resolve_target_transport(self)

    def _finalize_after_drift(self, ctx: AgentTickContext) -> None:
        _finalize_after_drift(self, ctx)

    async def _run_tool_step(
        self,
        messages: list[dict],
        ctx: AgentTickContext,
        *,
        loop_tag: str,
        tool_choice: str | dict = "auto",
        schemas: list[dict] | None = None,
        retry_on_no_tool_call: bool = False,
    ) -> bool:
        return await _run_tool_step(
            self,
            messages,
            ctx,
            loop_tag=loop_tag,
            tool_choice=tool_choice,
            schemas=schemas,
            retry_on_no_tool_call=retry_on_no_tool_call,
        )

    @staticmethod
    def _append_tool_messages(
        messages: list[dict],
        *,
        tool_name: str,
        tool_args: dict,
        tool_call_id: str,
        result: str,
    ) -> None:
        _append_tool_messages(
            messages,
            tool_name=tool_name,
            tool_args=tool_args,
            tool_call_id=tool_call_id,
            result=result,
        )

    def _build_system_prompt(self) -> str:
        return _build_system_prompt()

    def _build_runtime_context_message(
        self,
        ctx: AgentTickContext,
        gateway_result: GatewayResult,
    ) -> dict[str, str]:
        return _build_runtime_context_message(
            cfg=self._cfg,
            session_key=self._session_key,
            tool_deps=self._tool_deps,
            workspace_context_fn=self._workspace_context_fn,
            ctx=ctx,
            gateway_result=gateway_result,
        )

    def _is_relationship_only_fallback(
        self,
        gateway_result: GatewayResult,
    ) -> bool:
        return _is_relationship_only_fallback(gateway_result)

    def _allow_relationship_only_fallback(self, ctx: AgentTickContext) -> bool:
        return _allow_relationship_only_fallback(
            llm_fn=self._llm_fn,
            ctx=ctx,
        )

    def _relationship_fallback_style_hint(self) -> str:
        return _relationship_fallback_style_hint(self._session_key)

    def _read_workspace_context_for_prompt(self) -> str:
        return _read_workspace_context_for_prompt(self._workspace_context_fn)

    def _render_alert_block(self, alerts: list[dict]) -> str:
        return _render_alert_block(alerts)

    def _render_content_block(
        self,
        content_meta: list[dict],
        content_store: dict[str, str],
    ) -> str:
        return _render_content_block(content_meta, content_store)

    def _render_context_block(self, context: list[dict]) -> str:
        return _render_context_block(context, self._cfg)

    def _record_tick_log_start(self, ctx: AgentTickContext) -> None:
        _record_tick_log_start(
            state_store=self._state_store,
            session_key=self._session_key,
            ctx=ctx,
        )

    def _record_tick_log_finish(
        self,
        ctx: AgentTickContext,
        *,
        gate_exit: str | None = None,
        result: TurnResult | None = None,
    ) -> None:
        _record_tick_log_finish(
            state_store=self._state_store,
            session_key=self._session_key,
            ctx=ctx,
            gate_exit=gate_exit,
            result=result,
        )
        self._last_log_result = result

    def _record_tick_step(
        self,
        ctx: AgentTickContext,
        *,
        phase: str,
        tool_name: str,
        tool_call_id: str,
        tool_args: dict[str, Any],
        tool_result_text: str,
    ) -> None:
        _record_tick_step(
            state_store=self._state_store,
            ctx=ctx,
            phase=phase,
            tool_name=tool_name,
            tool_call_id=tool_call_id,
            tool_args=tool_args,
            tool_result_text=tool_result_text,
        )
