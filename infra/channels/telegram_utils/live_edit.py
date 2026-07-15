"""Telegram live message 的编辑队列与文本消息生命周期。"""

import asyncio
import html
import logging
from collections.abc import Awaitable, Callable
from typing import TypeVar

from telegram import Bot
from telegram.error import BadRequest, NetworkError, RetryAfter, TimedOut

from .limiter import TelegramOutboundLimiter
from .rendering import (
    _is_telegram_html_parse_error,
    _is_telegram_message_not_modified_error,
)
from .sending import _utf16_cut

logger = logging.getLogger("infra.channels.telegram_utils")
_T = TypeVar("_T")
_LIVE_MESSAGE_LIMIT = 3900
_LIVE_EDIT_MIN_INTERVAL_S = 1.0
_LIVE_MAX_FLOOD_STRIKES = 3
_LIVE_MAX_INLINE_RETRY_S = 2.0
_LIVE_MAX_BACKOFF_S = 10.0

class TelegramLiveEditQueue:
    def __init__(
        self,
        min_interval_s: float = _LIVE_EDIT_MIN_INTERVAL_S,
        limiter: TelegramOutboundLimiter | None = None,
    ) -> None:
        self._min_interval_s = min_interval_s
        self._limiter = limiter
        self._locks: dict[int, asyncio.Lock] = {}
        self._next_allowed_at: dict[int, float] = {}
        self._flood_strikes: dict[int, int] = {}
        self._current_interval_s: dict[int, float] = {}

    async def reserve(self, chat_id: int, *, label: str) -> None:
        lock = self._locks.setdefault(chat_id, asyncio.Lock())
        async with lock:
            await self._wait_for_slot(chat_id)
            self._mark_used(chat_id)
            logger.debug("[telegram] live queue reserved: %s chat_id=%s", label, chat_id)

    async def run(
        self,
        chat_id: int,
        *,
        label: str,
        force: bool = False,
        action: Callable[[], Awaitable[_T]],
    ) -> _T | None:
        if self._limiter is not None:
            strikes = self._flood_strikes.get(chat_id, 0)
            if strikes >= _LIVE_MAX_FLOOD_STRIKES and not force:
                logger.warning(
                    "[telegram] %s live 更新因连续限流跳过 chat_id=%s strikes=%d",
                    label,
                    chat_id,
                    strikes,
                )
                return None
            try:
                result = await self._limiter.run(
                    chat_id,
                    kind="edit" if label.startswith("edit_") else "send",
                    label=label,
                    action=action,
                    max_attempts=1,
                )
                self._flood_strikes[chat_id] = 0
                return result
            except RetryAfter as e:
                strikes = self._record_flood(chat_id)
                logger.warning(
                    "[telegram] %s live 更新命中限流，跳过本帧 chat_id=%s strikes=%d err=%s",
                    label,
                    chat_id,
                    strikes,
                    e,
                )
                return None
            except (TimedOut, NetworkError) as e:
                logger.warning("[telegram] %s live 更新失败，已跳过: %s", label, e)
                return None
        lock = self._locks.setdefault(chat_id, asyncio.Lock())
        async with lock:
            strikes = self._flood_strikes.get(chat_id, 0)
            if strikes >= _LIVE_MAX_FLOOD_STRIKES and not force:
                logger.warning(
                    "[telegram] %s live 更新因连续限流跳过 chat_id=%s strikes=%d",
                    label,
                    chat_id,
                    strikes,
                )
                return None
            for attempt in range(1, 4):
                await self._wait_for_slot(chat_id)
                try:
                    result = await action()
                    self._mark_used(chat_id)
                    self._flood_strikes[chat_id] = 0
                    self._current_interval_s[chat_id] = self._min_interval_s
                    return result
                except RetryAfter as e:
                    strikes = self._record_flood(chat_id)
                    delay = max(float(getattr(e, "retry_after", 1.0) or 1.0), self._interval(chat_id))
                    self._next_allowed_at[chat_id] = asyncio.get_running_loop().time() + delay
                    logger.warning(
                        "[telegram] %s 命中限流，延后 live 更新 attempt=%d/3 delay=%.1fs strikes=%d",
                        label,
                        attempt,
                        delay,
                        strikes,
                    )
                    if (
                        float(getattr(e, "retry_after", 1.0) or 1.0) > _LIVE_MAX_INLINE_RETRY_S
                        or strikes >= _LIVE_MAX_FLOOD_STRIKES
                    ):
                        return None
                    await asyncio.sleep(delay)
                except (TimedOut, NetworkError) as e:
                    self._mark_used(chat_id)
                    logger.warning("[telegram] %s live 更新失败，跳过: %s", label, e)
                    return None
            logger.warning("[telegram] %s live 更新多次限流，已跳过", label)
            return None

    async def _wait_for_slot(self, chat_id: int) -> None:
        now = asyncio.get_running_loop().time()
        next_allowed = self._next_allowed_at.get(chat_id, 0.0)
        if now < next_allowed:
            await asyncio.sleep(next_allowed - now)

    def _mark_used(self, chat_id: int) -> None:
        self._next_allowed_at[chat_id] = asyncio.get_running_loop().time() + self._interval(chat_id)

    def _interval(self, chat_id: int) -> float:
        return self._current_interval_s.get(chat_id, self._min_interval_s)

    def _record_flood(self, chat_id: int) -> int:
        strikes = self._flood_strikes.get(chat_id, 0) + 1
        self._flood_strikes[chat_id] = strikes
        current = self._current_interval_s.get(chat_id, self._min_interval_s)
        self._current_interval_s[chat_id] = min(current * 2, _LIVE_MAX_BACKOFF_S)
        return strikes


class TelegramLiveTextMessage:
    def __init__(
        self,
        bot: Bot,
        queue: TelegramLiveEditQueue,
        chat_id: int,
    ) -> None:
        self._bot = bot
        self._queue = queue
        self._chat_id = int(chat_id)
        self._message_id: int | None = None
        self._last_plain = ""
        self._update_lock = asyncio.Lock()

    async def update(
        self,
        text: str,
        *,
        html_text: str | None = None,
        force: bool = False,
    ) -> None:
        async with self._update_lock:
            await self._update_locked(text, html_text=html_text, force=force)

    async def _update_locked(
        self,
        text: str,
        *,
        html_text: str | None = None,
        force: bool = False,
    ) -> None:
        plain = _clip_live_text(text.strip())
        if not plain:
            return
        if not force and plain == self._last_plain:
            return
        html_body = html_text or f"<pre>{html.escape(plain)}</pre>"
        if self._message_id is None:
            sent = await self._queue.run(
                self._chat_id,
                label="send_message(live)",
                action=lambda: _send_live_message(
                    self._bot,
                    self._chat_id,
                    html_body,
                    plain,
                ),
            )
            if sent is None:
                return
            self._message_id = int(getattr(sent, "message_id", 0) or 0) or None
            self._last_plain = plain
            return
        ok = await self._queue.run(
            self._chat_id,
            label="edit_message(live)",
            force=force,
            action=lambda: _edit_live_message(
                self._bot,
                self._chat_id,
                self._message_id,
                html_body,
                plain,
            ),
        )
        if ok:
            self._last_plain = plain

    async def delete(self) -> None:
        if self._message_id is None:
            return
        message_id = self._message_id
        try:
            ok = await self._queue.run(
                self._chat_id,
                label="delete_message(live)",
                force=True,
                action=lambda: self._bot.delete_message(
                    chat_id=self._chat_id,
                    message_id=message_id,
                ),
            )
            if ok is not None:
                self._message_id = None
                self._last_plain = ""
        except RetryAfter as e:
            logger.warning("[telegram] live 预览删除命中限流，已跳过: %s", e)
        except (TimedOut, NetworkError) as e:
            logger.warning("[telegram] live 预览删除失败，已跳过: %s", e)


def _clip_live_text(text: str) -> str:
    if len(text.encode("utf-16-le")) // 2 <= _LIVE_MESSAGE_LIMIT:
        return text
    suffix = "\n..."
    cut = _utf16_cut(text, _LIVE_MESSAGE_LIMIT - len(suffix))
    return text[:cut] + suffix

async def _send_live_message(
    bot: Bot,
    chat_id: int,
    html_text: str,
    plain_text: str,
) -> object:
    try:
        return await bot.send_message(
            chat_id=chat_id,
            text=html_text,
            parse_mode="HTML",
        )
    except Exception as e:
        if not _is_telegram_html_parse_error(e):
            raise
        logger.warning("[telegram] live HTML 解析失败，降级纯文本: %s", e)
        return await bot.send_message(chat_id=chat_id, text=plain_text)


async def _edit_live_message(
    bot: Bot,
    chat_id: int,
    message_id: int | None,
    html_text: str,
    plain_text: str,
) -> bool:
    try:
        await bot.edit_message_text(
            chat_id=chat_id,
            message_id=message_id,
            text=html_text,
            parse_mode="HTML",
        )
        return True
    except BadRequest as e:
        if _is_telegram_message_not_modified_error(e):
            return True
        if not _is_telegram_html_parse_error(e):
            raise
        logger.warning("[telegram] live edit HTML 解析失败，降级纯文本: %s", e)
        await bot.edit_message_text(
            chat_id=chat_id,
            message_id=message_id,
            text=plain_text,
        )
        return True
    except Exception as e:
        if not _is_telegram_html_parse_error(e):
            raise
        logger.warning("[telegram] live edit HTML 解析失败，降级纯文本: %s", e)
        await bot.edit_message_text(
            chat_id=chat_id,
            message_id=message_id,
            text=plain_text,
        )
        return True
