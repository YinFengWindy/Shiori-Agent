"""主动回复的首次发送、多渠道重试与目标 transport 管理。"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import replace
from datetime import datetime, timezone
from typing import Any, Awaitable, Callable, Protocol

from agent.turns.result import TurnResult
from proactive_v2.context import AgentTickContext

from .types import ResolveResult

logger = logging.getLogger(__name__)

MULTI_CHANNEL_RETRY_WAIT_SECONDS = 5 * 60


class ProactiveDeliveryHost(Protocol):
    """发送阶段访问 pipeline 状态所需的最小宿主契约。"""

    _cfg: Any
    _session_key: str
    _turn_orchestrator: Any
    _last_user_at_fn: Callable[[], datetime | None]
    _target_transport_fn: Callable[[], tuple[str, str]] | None
    _target_transports_fn: Callable[[], list[tuple[str, str]]] | None
    _retry_wait_fn: Callable[[float], Awaitable[None]] | None
    _retry_task: asyncio.Task[None] | None
    _retry_cancel_event: asyncio.Event

    def _record_tick_log_finish(
        self,
        ctx: AgentTickContext,
        *,
        gate_exit: str | None = None,
        result: TurnResult | None = None,
    ) -> None: ...

    def _resolve_target_transports(self) -> list[tuple[str, str]]: ...

    async def cancel_pending_retries(self) -> None: ...

    async def _deliver_retries(
        self,
        *,
        transports: list[tuple[str, str]],
        result: TurnResult,
        sent_at: datetime,
    ) -> None: ...

    async def _wait_for_retry_or_user_reply(self, delay: float) -> bool: ...

    def _has_user_replied_since(self, sent_at: datetime) -> bool: ...

    def _resolve_target_transport(self) -> tuple[str, str] | None: ...


async def deliver_execute(
    pipeline: ProactiveDeliveryHost,
    ctx: AgentTickContext,
    decision: ResolveResult,
) -> float | None:
    """记录裁定并通过 orchestrator 执行首次发送和后台重试。"""

    pipeline._record_tick_log_finish(ctx, result=decision.result)
    if pipeline._turn_orchestrator is None:
        raise RuntimeError("proactive turn_orchestrator is required")
    transports = list(ctx.target_transports or pipeline._resolve_target_transports())
    if not transports:
        raise RuntimeError("proactive target transport unavailable at delivery time")

    await pipeline.cancel_pending_retries()
    pipeline._retry_cancel_event = asyncio.Event()
    target_channel, target_chat_id = transports[0]
    sent_at = datetime.now(timezone.utc)
    sent = await pipeline._turn_orchestrator.handle_proactive_turn(
        result=decision.result,
        session_key=pipeline._session_key,
        channel=target_channel,
        chat_id=target_chat_id,
    )
    if not sent:
        return 0.0

    retry_result = replace(
        decision.result,
        side_effects=[],
        success_side_effects=[],
        failure_side_effects=[],
    )
    if transports[1:]:
        pipeline._retry_task = asyncio.create_task(
            pipeline._deliver_retries(
                transports=transports[1:],
                result=retry_result,
                sent_at=sent_at,
            ),
            name=f"proactive-retries:{pipeline._session_key}",
        )
    return 0.0


async def deliver_retries(
    pipeline: ProactiveDeliveryHost,
    *,
    transports: list[tuple[str, str]],
    result: TurnResult,
    sent_at: datetime,
) -> None:
    """在首次发送后依次尝试其余目标渠道。"""

    try:
        for target_channel, target_chat_id in transports:
            if not await pipeline._wait_for_retry_or_user_reply(
                MULTI_CHANNEL_RETRY_WAIT_SECONDS
            ):
                logger.info(
                    "[proactive_v2] multi-channel retry stopped: user replied session=%s",
                    pipeline._session_key,
                )
                return
            if pipeline._has_user_replied_since(sent_at):
                logger.info(
                    "[proactive_v2] multi-channel retry stopped: user replied session=%s",
                    pipeline._session_key,
                )
                return
            await pipeline._turn_orchestrator.handle_proactive_turn(
                result=result,
                session_key=pipeline._session_key,
                channel=target_channel,
                chat_id=target_chat_id,
                record_proactive_state=False,
            )
    except asyncio.CancelledError:
        raise
    except Exception:
        logger.exception(
            "[proactive_v2] multi-channel retry failed session=%s",
            pipeline._session_key,
        )


async def wait_for_retry_or_user_reply(
    pipeline: ProactiveDeliveryHost,
    delay: float,
) -> bool:
    """等待重试间隔或用户回复，并返回是否继续发送。"""

    if pipeline._retry_cancel_event.is_set():
        return False
    wait_fn = pipeline._retry_wait_fn or asyncio.sleep
    delay_task = asyncio.ensure_future(wait_fn(delay))
    reply_task = asyncio.create_task(pipeline._retry_cancel_event.wait())
    try:
        done, _ = await asyncio.wait(
            {delay_task, reply_task},
            return_when=asyncio.FIRST_COMPLETED,
        )
        if delay_task not in done:
            return False
        await delay_task
        return not pipeline._retry_cancel_event.is_set()
    finally:
        for task in (delay_task, reply_task):
            if not task.done():
                task.cancel()
        await asyncio.gather(delay_task, reply_task, return_exceptions=True)


def notify_user_reply(pipeline: ProactiveDeliveryHost) -> None:
    """取消当前 session 的多渠道后台重试。"""

    pipeline._retry_cancel_event.set()
    task = pipeline._retry_task
    if task is not None and not task.done() and task is not asyncio.current_task():
        task.cancel()


async def cancel_pending_retries(pipeline: ProactiveDeliveryHost) -> None:
    """等待并清理当前 session 的多渠道后台重试任务。"""

    pipeline._retry_cancel_event.set()
    task = pipeline._retry_task
    if task is None or task is asyncio.current_task():
        return
    if not task.done():
        task.cancel()
    try:
        await task
    except asyncio.CancelledError:
        pass
    finally:
        if pipeline._retry_task is task:
            pipeline._retry_task = None


def has_user_replied_since(
    pipeline: ProactiveDeliveryHost,
    sent_at: datetime,
) -> bool:
    """检查用户是否在首次主动发送后回复。"""

    last_user_at = pipeline._last_user_at_fn()
    if last_user_at is None:
        return False
    if last_user_at.tzinfo is None:
        last_user_at = last_user_at.replace(tzinfo=timezone.utc)
    return last_user_at > sent_at


def resolve_target_transports(
    pipeline: ProactiveDeliveryHost,
) -> list[tuple[str, str]]:
    """解析全部可用目标渠道，并回退到单渠道配置。"""

    if pipeline._target_transports_fn is not None:
        try:
            raw_transports = pipeline._target_transports_fn()
        except Exception as exc:
            logger.debug("[proactive_v2] target_transports unavailable: %s", exc)
        else:
            transports = [
                (str(channel).strip(), str(chat_id).strip())
                for channel, chat_id in raw_transports
                if str(channel).strip() and str(chat_id).strip()
            ]
            if transports:
                return transports
    transport = pipeline._resolve_target_transport()
    return [transport] if transport is not None else []


def resolve_target_transport(
    pipeline: ProactiveDeliveryHost,
) -> tuple[str, str] | None:
    """解析单个目标渠道，并回退到默认渠道配置。"""

    if pipeline._target_transport_fn is not None:
        try:
            channel, chat_id = pipeline._target_transport_fn()
        except Exception as exc:
            logger.debug("[proactive_v2] target_transport unavailable: %s", exc)
        else:
            resolved_channel = str(channel or "").strip()
            resolved_chat_id = str(chat_id or "").strip()
            if resolved_channel and resolved_chat_id:
                return resolved_channel, resolved_chat_id
    fallback_channel = str(pipeline._cfg.default_channel or "").strip()
    fallback_chat_id = str(pipeline._cfg.default_chat_id or "").strip()
    if fallback_channel and fallback_chat_id:
        return fallback_channel, fallback_chat_id
    return None
