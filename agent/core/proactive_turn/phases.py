"""主动回复 Gate、Fetch 与 drift 收尾阶段实现。"""

from __future__ import annotations

import logging
from typing import Any, Protocol

from core.common.diagnostic_log import diagnostic_line
from proactive_v2.context import AgentTickContext
from proactive_v2.gateway import DataGateway, GatewayDeps, GatewayResult

from .types import FeedResult, GateResult
from .gates import ProactiveGateContext, ProactiveMode

logger = logging.getLogger(__name__)


class ProactivePhaseHost(Protocol):
    """主动阶段实现访问 pipeline 状态所需的最小宿主契约。"""

    _cfg: Any
    _session_key: str
    _state_store: Any
    _passive_busy_fn: Any
    _proactive_gates: Any
    _gateway_deps: Any
    _tool_deps: Any
    _llm_fn: Any
    _drift_pipeline: Any
    _last_gateway_result: GatewayResult | None
    last_ctx: AgentTickContext | None

    def _resolve_target_transports(self) -> list[tuple[str, str]]: ...

    def _allow_relationship_only_fallback(self, ctx: AgentTickContext) -> bool: ...

    def _build_system_prompt(self) -> str: ...

    def _build_runtime_context_message(
        self,
        ctx: AgentTickContext,
        gateway_result: GatewayResult,
    ) -> dict[str, str]: ...

    def _is_relationship_only_fallback(
        self,
        gateway_result: GatewayResult,
    ) -> bool: ...

    def _relationship_fallback_style_hint(self) -> str: ...

    def _record_tick_log_finish(self, ctx: AgentTickContext, **kwargs: Any) -> None: ...


def _log_content_candidates(gateway_result: GatewayResult) -> None:
    if not gateway_result.content_meta:
        logger.info("[proactive_v2] content candidates: 0")
        return
    lines: list[str] = []
    for index, item in enumerate(gateway_result.content_meta, 1):
        title = str(item.get("title") or "").strip() or "(no title)"
        source = str(item.get("source") or "").strip()
        line = f"[{index}] {title}"
        if source:
            line += f" | source={source}"
        lines.append(line)
    logger.info(
        "[proactive_v2] content candidates: %d\n%s",
        len(gateway_result.content_meta),
        "\n".join(lines),
    )


def gate_check(pipeline: ProactivePhaseHost, ctx: AgentTickContext) -> GateResult:
    """逐条件判断本轮是否应该启动主动处理。"""

    transports = pipeline._resolve_target_transports()
    if not transports:
        logger.debug("[proactive_v2] gate: no chat_id → blocked")
        return GateResult(blocked=True, reason="no_target", base_score=None)
    ctx.target_transports = transports
    ctx.target_channel, ctx.target_chat_id = transports[0]

    if pipeline._passive_busy_fn and pipeline._passive_busy_fn(pipeline._session_key):
        logger.debug("[proactive_v2] gate: passive_busy → blocked")
        return GateResult(blocked=True, reason="busy", base_score=None)

    gate_result = pipeline._proactive_gates.evaluate(
        ProactiveGateContext(
            tick_id=ctx.tick_id,
            session_key=pipeline._session_key,
            now_utc=ctx.now_utc,
            target_transports=tuple(transports),
        )
    )
    ctx.gate_trace = gate_result.trace
    for item in gate_result.trace:
        logger.info(
            diagnostic_line(
                "ProactiveTurnPipeline._gate_check",
                event="plugin_gate",
                flow="proactive",
                phase="pregate",
                session=pipeline._session_key,
                tick=ctx.tick_id,
                action=item.decision,
                reason=item.reason or "-",
                duration_ms=item.duration_ms,
                note=f"gate={item.gate_name} priority={item.priority}",
            )
        )
    if gate_result.blocked:
        logger.debug("[proactive_v2] plugin gate blocked: %s", gate_result.reason)
        return GateResult(blocked=True, reason=gate_result.reason, base_score=None)

    return GateResult(
        blocked=False,
        reason=gate_result.reason,
        base_score=None,
        context_as_fallback_open=False,
        activation=gate_result.activation,
    )


async def fetch_pull(
    pipeline: ProactivePhaseHost,
    ctx: AgentTickContext,
) -> FeedResult:
    """拉取本轮数据源并构建模型输入消息。"""

    gateway_deps = pipeline._gateway_deps or GatewayDeps(
        alert_fn=None,
        feed_fn=None,
        context_fn=None,
        web_fetch_tool=pipeline._tool_deps.web_fetch_tool,
        max_chars=pipeline._tool_deps.max_chars,
        content_limit=pipeline._cfg.agent_tick_content_limit,
    )
    gateway = DataGateway(
        alert_fn=gateway_deps.alert_fn,
        feed_fn=gateway_deps.feed_fn,
        context_fn=gateway_deps.context_fn,
        web_fetch_tool=gateway_deps.web_fetch_tool,
        max_chars=gateway_deps.max_chars,
        content_limit=gateway_deps.content_limit,
    )
    gateway_result = await gateway.run()
    pipeline._last_gateway_result = gateway_result
    _log_content_candidates(gateway_result)
    logger.info(
        diagnostic_line(
            "ProactiveTurnPipeline._fetch_pull",
            event="end",
            flow="proactive",
            phase="gateway",
            session=pipeline._session_key,
            tick=ctx.tick_id,
            action="fetched",
            counts=f"alerts:{len(gateway_result.alerts)},content:{len(gateway_result.content_meta)},context:{len(gateway_result.context)}",
        )
    )

    ctx.mark_alerts_prefetched(gateway_result.alerts)
    fetched_contents = [
        {
            "id": meta["id"].split(":", 1)[1] if ":" in meta["id"] else meta["id"],
            "event_id": meta["id"].split(":", 1)[1] if ":" in meta["id"] else meta["id"],
            "ack_server": meta["id"].split(":", 1)[0],
            "title": meta.get("title") or "",
            "source": meta.get("source") or "",
            "url": meta.get("url") or "",
            "published_at": meta.get("published_at") or "",
        }
        for meta in gateway_result.content_meta
    ]
    ctx.mark_contents_prefetched(fetched_contents, gateway_result.content_store)
    ctx.mark_context_prefetched(gateway_result.context)

    if (
        not gateway_result.alerts
        and not gateway_result.content_meta
        and not ctx.context_as_fallback_open
    ):
        if pipeline._allow_relationship_only_fallback(ctx):
            ctx.active_gate = ctx.selected_gate
            logger.info(
                "[proactive_v2] fetch: no data but relationship gate passed → relationship fallback"
            )
        elif pipeline._drift_pipeline is not None and pipeline._cfg.drift_enabled:
            last_drift_at = pipeline._state_store.get_last_drift_at(
                pipeline._session_key
            )
            min_interval_hours = max(
                0,
                int(getattr(pipeline._cfg, "drift_min_interval_hours", 0) or 0),
            )
            if (
                last_drift_at is not None
                and min_interval_hours > 0
                and (ctx.now_utc - last_drift_at).total_seconds()
                < min_interval_hours * 3600
            ):
                logger.info(
                    diagnostic_line(
                        "ProactiveTurnPipeline._fetch_pull",
                        event="skip",
                        flow="proactive",
                        phase="gateway",
                        session=pipeline._session_key,
                        tick=ctx.tick_id,
                        action="skip",
                        reason="cooldown",
                        counts="alerts:0,content:0,context:0",
                    )
                )
                logger.info(
                    "[proactive_v2] fetch: drift blocked by interval last_drift_at=%s min_interval_hours=%d",
                    last_drift_at.isoformat(),
                    min_interval_hours,
                )
                ctx.terminal_action = "skip"
                ctx.skip_reason = "no_content"
                pipeline.last_ctx = ctx
                return FeedResult(drift_entered=False, base_score=None)
            logger.info("[proactive_v2] fetch: empty gateway, attempting drift")
            entered_drift = await pipeline._drift_pipeline.run(ctx, pipeline._llm_fn)
            if entered_drift:
                pipeline._state_store.mark_drift_run(
                    pipeline._session_key,
                    ctx.now_utc,
                )
                logger.info(
                    "[proactive_v2] fetch: drift entered, message_sent=%s",
                    ctx.drift_message_sent,
                )
                pipeline.last_ctx = ctx
                return FeedResult(drift_entered=True, base_score=0.0)
            logger.info("[proactive_v2] fetch: drift not entered")
        else:
            logger.info("[proactive_v2] fetch: no data and fallback off → skip")
            logger.info(
                diagnostic_line(
                    "ProactiveTurnPipeline._fetch_pull",
                    event="skip",
                    flow="proactive",
                    phase="gateway",
                    session=pipeline._session_key,
                    tick=ctx.tick_id,
                    action="skip",
                    reason="no_content",
                    counts="alerts:0,content:0,context:0",
                )
            )
            ctx.terminal_action = "skip"
            ctx.skip_reason = "no_content"
            pipeline.last_ctx = ctx
            return FeedResult(drift_entered=False, base_score=None)

    if pipeline._llm_fn is None:
        pipeline.last_ctx = ctx
        return FeedResult(drift_entered=False, base_score=None)

    system_msg = {"role": "system", "content": pipeline._build_system_prompt()}
    runtime_context_msg = pipeline._build_runtime_context_message(ctx, gateway_result)
    kickoff_content = (
        "开始本轮 proactive 处理。"
        "请基于上面的候选内容和规则，必须通过工具逐步完成分类，"
        "最后通过 message_push + finish_turn(decision=reply)，或 finish_turn(decision=skip, reason=...) 收尾。"
    )
    active_mode = ctx.active_gate.mode if ctx.active_gate is not None else None
    scene_followup_mode = (
        active_mode == ProactiveMode.SCENE_FOLLOWUP
        and pipeline._is_relationship_only_fallback(gateway_result)
    )
    if scene_followup_mode:
        scene_followup_attempt = int(
            (ctx.active_gate.metadata.get("attempt_index", 0) if ctx.active_gate else 0)
            or 0
        )
        kickoff_content = (
            "开始本轮同一场景追问。"
            f"这是本场景第 {scene_followup_attempt + 1} 次追问，间隔会逐次缩短。"
            "先用 get_recent_chat 判断最近对话是否仍属于同一个未结束场景。"
            "如果场景仍在继续，应该直接 message_push 一条自然的承接或追问，再 finish_turn(decision=reply)。"
            "如果已经告别、睡觉、转入新话题，必须 finish_turn(decision=skip, reason=scene_changed) 关闭本场景追问。"
            "不要因为寂寞值不足而跳过同场景追问。"
            + pipeline._relationship_fallback_style_hint()
        )
    elif pipeline._is_relationship_only_fallback(gateway_result):
        kickoff_content = (
            "开始本轮 proactive 处理。"
            "本轮已通过 loneliness gate，但当前没有 alert/content/context 候选。"
            "这一轮优先尝试纯关系向 fallback，不要改走 drift。"
            "先用 get_recent_chat 判断最近是否有自然延伸的话题；"
            "只要能自然接上，就应该直接 message_push 一条轻量的关系向主动消息并 finish_turn(decision=reply)。"
            "只有在 recent_chat 明确看不出任何自然切口，或明显不适合打扰时，才 finish_turn(decision=skip, reason=no_content)。"
            + pipeline._relationship_fallback_style_hint()
        )
    kickoff_msg = {"role": "user", "content": kickoff_content}
    return FeedResult(
        drift_entered=False,
        base_score=None,
        messages=[system_msg, runtime_context_msg, kickoff_msg],
    )


def finalize_after_drift(
    pipeline: ProactivePhaseHost,
    ctx: AgentTickContext,
) -> None:
    """drift 进入后跳过正常 post-loop 并收尾。"""

    logger.info(
        "[proactive_v2] drift entered, skipping normal post_loop message_sent=%s finished=%s",
        ctx.drift_message_sent,
        ctx.drift_finished,
    )
    pipeline._record_tick_log_finish(ctx)
    ctx.content_store.clear()
