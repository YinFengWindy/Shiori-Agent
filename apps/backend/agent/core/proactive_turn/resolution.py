"""主动回复的 delivery key、ACK、副作用与最终裁定。"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from hashlib import sha1
from typing import Any, Awaitable, Callable, Literal, Protocol
from urllib.parse import urlsplit, urlunsplit

from agent.turns.result import TurnOutbound, TurnResult, TurnTrace
from core.common.diagnostic_log import diagnostic_line
from proactive_v2.context import AgentTickContext

from .gates import ProactiveGateCompletion
from .types import ResolveResult

logger = logging.getLogger(__name__)

_CITED_ACK_TTL = 168
_UNCITED_ACK_TTL = 24
_POST_GUARD_ACK_TTL = 24
_DISCARDED_ACK_TTL = 720


class ProactiveResolutionHost(Protocol):
    """裁定阶段访问 pipeline 状态所需的最小宿主契约。"""

    _cfg: Any
    _session_key: str
    _state_store: Any
    _deduper: Any
    _tool_deps: Any
    _recent_proactive_fn: Callable[[], list] | None
    _proactive_gates: Any


@dataclass
class _CallbackSideEffect:
    callback: Callable[[], Awaitable[None]]
    name: str = "callback"

    async def run(self) -> None:
        await self.callback()


def _normalize_delivery_url(raw: str) -> str:
    text = str(raw or "").strip()
    if not text:
        return ""
    parts = urlsplit(text)
    path = parts.path.rstrip("/") or parts.path
    return urlunsplit((parts.scheme.lower(), parts.netloc.lower(), path, parts.query, ""))


def _build_delivery_refs(ctx: AgentTickContext) -> list[str]:
    if not ctx.cited_item_ids:
        return []
    content_map = {
        f"{event.get('ack_server', '')}:{event.get('event_id') or event.get('id', '')}": event
        for event in ctx.fetched_contents
        if event.get("ack_server") and (event.get("event_id") or event.get("id"))
    }
    refs: list[str] = []
    for key in sorted(set(ctx.cited_item_ids)):
        meta = content_map.get(key)
        if meta is None:
            refs.append(f"id:{key}")
            continue
        url = _normalize_delivery_url(str(meta.get("url") or ""))
        if url:
            refs.append(f"url:{url}")
            continue
        source = str(meta.get("source") or meta.get("source_name") or "").strip().lower()
        title = str(meta.get("title") or "").strip().lower()
        if title:
            refs.append(f"title:{source}|{title}")
            continue
        refs.append(f"id:{key}")
    return sorted(set(refs))


def build_delivery_key(ctx: AgentTickContext) -> str:
    """根据引用来源或最终消息构建稳定的投递去重键。"""

    refs = _build_delivery_refs(ctx)
    if refs and any(not ref.startswith("id:") for ref in refs):
        key_src = json.dumps(refs)
    elif ctx.cited_item_ids:
        key_src = json.dumps(sorted(ctx.cited_item_ids))
    else:
        key_src = ctx.final_message[:500]
    return sha1(key_src.encode()).hexdigest()[:16]


async def ack_discarded(ctx: AgentTickContext, ack_fn) -> None:
    """按丢弃条目的长 TTL 执行 ACK。"""

    if ack_fn is None:
        return
    for key in ctx.discarded_item_ids:
        await ack_fn(key, _DISCARDED_ACK_TTL)


async def ack_post_guard_fail(ctx: AgentTickContext, ack_fn, *, alert_ack_fn=None) -> None:
    """对通过模型判断但未通过发送后置 guard 的条目执行 ACK。"""

    if ack_fn is None:
        return
    fetched_alert_keys = {
        f"{event['ack_server']}:{event.get('event_id') or event.get('id', '')}"
        for event in ctx.fetched_alerts
    }
    cited_set = set(ctx.cited_item_ids)

    async def _ack_alert(key: str) -> None:
        if alert_ack_fn is not None:
            await alert_ack_fn(key)
        else:
            await ack_fn(key, _POST_GUARD_ACK_TTL)

    for key in cited_set - fetched_alert_keys:
        await ack_fn(key, _POST_GUARD_ACK_TTL)
    for key in cited_set & fetched_alert_keys:
        await _ack_alert(key)
    for key in fetched_alert_keys - cited_set:
        await _ack_alert(key)
    for key in (ctx.interesting_item_ids - cited_set) - fetched_alert_keys:
        await ack_fn(key, _POST_GUARD_ACK_TTL)
    for key in ctx.discarded_item_ids:
        await ack_fn(key, _DISCARDED_ACK_TTL)


async def ack_on_success(ctx: AgentTickContext, ack_fn, *, alert_ack_fn=None) -> None:
    """按引用、未引用和丢弃状态执行成功投递后的 ACK。"""

    if ack_fn is None:
        return
    fetched_alert_keys = {
        f"{event['ack_server']}:{event.get('event_id') or event.get('id', '')}"
        for event in ctx.fetched_alerts
    }
    fetched_content_keys = {
        f"{event['ack_server']}:{event.get('event_id') or event.get('id', '')}"
        for event in ctx.fetched_contents
    }
    cited_set = set(ctx.cited_item_ids)
    for key in cited_set & fetched_content_keys:
        await ack_fn(key, _CITED_ACK_TTL)
    for key in cited_set & fetched_alert_keys:
        if alert_ack_fn is not None:
            await alert_ack_fn(key)
        else:
            await ack_fn(key, _CITED_ACK_TTL)
    for key in (ctx.interesting_item_ids - cited_set) - fetched_alert_keys:
        await ack_fn(key, _UNCITED_ACK_TTL)
    for key in ctx.discarded_item_ids:
        await ack_fn(key, _DISCARDED_ACK_TTL)


async def _mark_delivery(*, state_store: Any, session_key: str, delivery_key: str) -> None:
    state_store.mark_delivery(session_key, delivery_key)


async def _finalize_active_gate(
    gate_chain: Any,
    ctx: AgentTickContext,
    *,
    outcome: Literal["delivered", "closed"],
    reason: str = "",
) -> None:
    activation = ctx.active_gate
    if activation is None:
        return
    gate_chain.finalize(
        ProactiveGateCompletion(
            activation=activation,
            session_key=ctx.session_key,
            occurred_at=datetime.now(timezone.utc),
            outcome=outcome,
            reason=reason,
        )
    )


def _active_gate_close_effects(
    gate_chain: Any,
    ctx: AgentTickContext,
    *,
    reason: str,
) -> list[_CallbackSideEffect]:
    if ctx.active_gate is None:
        return []
    return [
        _CallbackSideEffect(
            callback=lambda: _finalize_active_gate(
                gate_chain,
                ctx,
                outcome="closed",
                reason=reason,
            ),
            name="finalize_active_gate_closed",
        )
    ]


async def resolve_decide(
    pipeline: ProactiveResolutionHost,
    ctx: AgentTickContext,
) -> ResolveResult:
    """裁定 skip/reply，并组装去重和 ACK 副作用。"""

    ack_fn = pipeline._tool_deps.ack_fn
    if ctx.terminal_action != "reply":
        logger.info(
            diagnostic_line(
                "ProactiveTurnPipeline._resolve_decide",
                event="resolve",
                flow="proactive",
                phase="resolve",
                session=pipeline._session_key,
                tick=ctx.tick_id,
                action="skip",
                reason=ctx.skip_reason or "no_content",
                counts=f"steps:{ctx.steps_taken},interesting:{len(ctx.interesting_item_ids)},discarded:{len(ctx.discarded_item_ids)}",
                note=ctx.skip_note or "-",
            )
        )
        logger.info(
            "[proactive_v2] resolve: action=%s steps=%d discarded=%d interesting=%d skip_reason=%s note=%s",
            ctx.terminal_action or "none",
            ctx.steps_taken,
            len(ctx.discarded_item_ids),
            len(ctx.interesting_item_ids),
            ctx.skip_reason,
            ctx.skip_note,
        )
        skip_side_effects = [
            _CallbackSideEffect(
                callback=lambda: ack_discarded(ctx, ack_fn),
                name="ack_discarded_skip",
            )
        ]
        if ctx.active_gate is not None and ctx.skip_reason in {"scene_changed", "no_content"}:
            skip_side_effects.extend(
                _active_gate_close_effects(
                    pipeline._proactive_gates,
                    ctx,
                    reason=ctx.skip_reason,
                )
            )
        return ResolveResult(
            action="skip",
            result=TurnResult(
                decision="skip",
                outbound=None,
                trace=TurnTrace(
                    source="proactive",
                    extra={
                        "steps_taken": ctx.steps_taken,
                        "skip_reason": ctx.skip_reason,
                        "skip_note": ctx.skip_note,
                    },
                ),
                side_effects=skip_side_effects,
            ),
        )

    delivery_key = build_delivery_key(ctx)
    if pipeline._state_store.is_delivery_duplicate(
        pipeline._session_key,
        delivery_key,
        pipeline._cfg.delivery_dedupe_hours,
    ):
        logger.info(
            diagnostic_line(
                "ProactiveTurnPipeline._resolve_decide",
                event="resolve",
                flow="proactive",
                phase="resolve",
                session=pipeline._session_key,
                tick=ctx.tick_id,
                action="skip",
                reason="already_sent_similar",
                counts=f"steps:{ctx.steps_taken},interesting:{len(ctx.interesting_item_ids)},discarded:{len(ctx.discarded_item_ids)}",
                note="delivery_dedupe",
            )
        )
        logger.info("[proactive_v2] resolve: delivery_dedupe hit")
        return ResolveResult(
            action="skip",
            result=TurnResult(
                decision="skip",
                outbound=None,
                evidence=list(ctx.cited_item_ids),
                trace=TurnTrace(
                    source="proactive",
                    extra={
                        "steps_taken": ctx.steps_taken,
                        "skip_reason": "already_sent_similar",
                        "dedupe": "delivery",
                    },
                ),
                side_effects=[
                    _CallbackSideEffect(
                        callback=lambda: ack_post_guard_fail(
                            ctx,
                            ack_fn,
                            alert_ack_fn=pipeline._tool_deps.alert_ack_fn,
                        ),
                        name="ack_post_guard_delivery",
                    ),
                    *(
                        _active_gate_close_effects(
                            pipeline._proactive_gates,
                            ctx,
                            reason="already_sent_similar",
                        )
                        if ctx.active_gate is not None
                        else []
                    ),
                ],
            ),
        )

    if pipeline._cfg.message_dedupe_enabled and pipeline._deduper is not None:
        recent_proactive = (
            pipeline._recent_proactive_fn()
            if pipeline._recent_proactive_fn is not None
            else []
        )
        is_dup, reason = await pipeline._deduper.is_duplicate(
            new_message=ctx.final_message,
            recent_proactive=recent_proactive,
            new_state_summary_tag="none",
        )
        if is_dup:
            logger.info(
                diagnostic_line(
                    "ProactiveTurnPipeline._resolve_decide",
                    event="resolve",
                    flow="proactive",
                    phase="resolve",
                    session=pipeline._session_key,
                    tick=ctx.tick_id,
                    action="skip",
                    reason="already_sent_similar",
                    counts=f"steps:{ctx.steps_taken},interesting:{len(ctx.interesting_item_ids)},discarded:{len(ctx.discarded_item_ids)}",
                    note=str(reason or "message_dedupe")[:160],
                )
            )
            logger.info("[proactive_v2] resolve: message_dedupe hit: %s", reason)
            return ResolveResult(
                action="skip",
                result=TurnResult(
                    decision="skip",
                    outbound=None,
                    evidence=list(ctx.cited_item_ids),
                    trace=TurnTrace(
                        source="proactive",
                        extra={
                            "steps_taken": ctx.steps_taken,
                            "skip_reason": "already_sent_similar",
                            "dedupe": "message",
                            "dedupe_note": str(reason or ""),
                        },
                    ),
                    side_effects=[
                        _CallbackSideEffect(
                            callback=lambda: ack_post_guard_fail(
                                ctx,
                                ack_fn,
                                alert_ack_fn=pipeline._tool_deps.alert_ack_fn,
                            ),
                            name="ack_post_guard_message",
                        ),
                        *(
                            _active_gate_close_effects(
                                pipeline._proactive_gates,
                                ctx,
                                reason="already_sent_similar",
                            )
                            if ctx.active_gate is not None
                            else []
                        ),
                    ],
                ),
            )

    logger.info(
        diagnostic_line(
            "ProactiveTurnPipeline._resolve_decide",
            event="resolve",
            flow="proactive",
            phase="resolve",
            session=pipeline._session_key,
            tick=ctx.tick_id,
            action="send",
            reason="-",
            counts=f"steps:{ctx.steps_taken},interesting:{len(ctx.interesting_item_ids)},discarded:{len(ctx.discarded_item_ids)},cited:{len(ctx.cited_item_ids)}",
        )
    )
    success_side_effects = [
        _CallbackSideEffect(
            callback=lambda: _mark_delivery(
                state_store=pipeline._state_store,
                session_key=pipeline._session_key,
                delivery_key=delivery_key,
            ),
            name="mark_delivery",
        ),
        _CallbackSideEffect(
            callback=lambda: ack_on_success(
                ctx,
                ack_fn,
                alert_ack_fn=pipeline._tool_deps.alert_ack_fn,
            ),
            name="ack_on_success",
        ),
    ]
    if ctx.active_gate is not None:
        success_side_effects.append(
            _CallbackSideEffect(
                callback=lambda: _finalize_active_gate(
                    pipeline._proactive_gates,
                    ctx,
                    outcome="delivered",
                ),
                name="finalize_active_gate_delivered",
            )
        )
    return ResolveResult(
        action="send",
        result=TurnResult(
            decision="reply",
            outbound=TurnOutbound(
                session_key=pipeline._session_key,
                content=ctx.final_message,
            ),
            evidence=list(ctx.cited_item_ids),
            trace=TurnTrace(
                source="proactive",
                extra={
                    "steps_taken": ctx.steps_taken,
                    "skip_reason": "",
                    "state_summary_tag": "none",
                },
            ),
            success_side_effects=success_side_effects,
            failure_side_effects=[
                _CallbackSideEffect(
                    callback=lambda: ack_discarded(ctx, ack_fn),
                    name="ack_discarded_send_fail",
                )
            ],
        ),
    )
