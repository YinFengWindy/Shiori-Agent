"""Telegram 单消息流式预览与编辑。"""

import asyncio
import html
import logging

from telegram import Bot
from telegram.error import BadRequest, NetworkError, RetryAfter, TimedOut

from .limiter import (
    TelegramOutboundLimiter,
    _run_outbound,
    _send_with_retry_result,
)
from .rendering import (
    _is_telegram_html_parse_error,
    _is_telegram_message_not_modified_error,
    render_telegram_preview_html,
)

logger = logging.getLogger("infra.channels.telegram_utils")
_STREAM_CHUNK_STEP = 120
_STREAM_PUSH_MIN_INTERVAL_S = 2.5
_STREAM_PUSH_MIN_CHARS = 200
_TELEGRAM_MSG_LIMIT = 4096
_THINKING_CAP = 800
_THINKING_MIN = 100
_PREVIEW_OVERHEAD = 80


def _ring_tail(text: str, cap: int) -> str:
    """保留文本最后 cap 个字符，超出部分用省略号标记。"""
    if cap <= 0:
        return ""
    if len(text) <= cap:
        return text
    return "…" + text[-(cap - 1):]


class TelegramStreamMessage:
    def __init__(
        self,
        bot: Bot,
        chat_id: int,
        limiter: TelegramOutboundLimiter | None = None,
    ) -> None:
        self._bot = bot
        self._chat_id = int(chat_id)
        self._limiter = limiter
        self._message_id: int | None = None
        self._reply_buffer = ""
        self._thinking_buffer = ""
        self._last_sent_plain = ""
        self._last_sent_at = 0.0
        self._edit_cooldown_until = 0.0

    # ------------------------------------------------------------------
    # public API
    # ------------------------------------------------------------------

    async def push_delta(
        self,
        delta: str | dict[str, str],
        *,
        force: bool = False,
    ) -> None:
        if self._chat_id <= 0:
            return
        if isinstance(delta, str):
            self._reply_buffer += delta
        else:
            self._reply_buffer += delta.get("content_delta", "")
            self._thinking_buffer += delta.get("thinking_delta", "")
        result = self._build_stream_preview()
        if result is None:
            return
        html_text, plain_text = result
        now = asyncio.get_running_loop().time()
        if not force and now < self._edit_cooldown_until:
            return
        if not force:
            grown = len(plain_text) - len(self._last_sent_plain)
            if (
                self._last_sent_plain
                and grown < _STREAM_PUSH_MIN_CHARS
                and now - self._last_sent_at < _STREAM_PUSH_MIN_INTERVAL_S
            ):
                return
        await self._send_or_edit(html_text, plain_text)
        self._last_sent_at = now

    async def finalize(self, text: str) -> None:
        self._reply_buffer = text or ""
        current = (text or "").strip()
        if not current:
            return
        await self._push_reply_text(current)

    # ------------------------------------------------------------------
    # preview 构建
    # ------------------------------------------------------------------

    def _build_stream_preview(self) -> tuple[str, str] | None:
        """构建流式预览 (html, plain)。thinking 用环形缓冲，reply 优先占预算。"""
        reply = self._reply_buffer.strip()
        thinking = self._thinking_buffer.strip()
        if not reply and not thinking:
            return None
        limit = _TELEGRAM_MSG_LIMIT

        # ---- 仅回复 ----
        if not thinking:
            trimmed = reply[:limit]
            return render_telegram_preview_html(trimmed), trimmed

        # ---- 仅思考 ----
        if not reply:
            cap = limit - _PREVIEW_OVERHEAD
            tail = _ring_tail(thinking, cap)
            plain = f"💭 {tail}"
            h = f"<blockquote>💭 <i>{html.escape(tail)}</i></blockquote>"
            return h, plain

        # ---- 双区域：reply 优先，thinking 取剩余 ----
        reply_need = min(len(reply), limit - _PREVIEW_OVERHEAD - _THINKING_MIN)
        t_budget = max(
            min(limit - reply_need - _PREVIEW_OVERHEAD, _THINKING_CAP),
            _THINKING_MIN,
        )
        r_budget = limit - t_budget - _PREVIEW_OVERHEAD

        tail = _ring_tail(thinking, t_budget)
        reply_trimmed = reply[:r_budget]

        plain = f"💭 {tail}\n\n{reply_trimmed}"
        h = (
            f"<blockquote>💭 <i>{html.escape(tail)}</i></blockquote>"
            f"\n{render_telegram_preview_html(reply_trimmed)}"
        )
        return h, plain

    # ------------------------------------------------------------------
    # 底层发送 / 编辑
    # ------------------------------------------------------------------

    async def _push_reply_text(self, text: str) -> None:
        """finalize 专用：发送纯回复文本（无思考前缀）。"""
        preview = text if len(text) <= _TELEGRAM_MSG_LIMIT else text[:_TELEGRAM_MSG_LIMIT]
        if preview == self._last_sent_plain:
            return
        html_text = render_telegram_preview_html(preview)
        await self._send_or_edit(html_text, preview)

    async def _send_or_edit(self, html_text: str, plain_text: str) -> None:
        """首次调用 send，后续 edit。成功后更新 _last_sent_plain。"""
        if plain_text == self._last_sent_plain and self._message_id is not None:
            return
        if self._message_id is None:
            sent = await _run_outbound(
                self._limiter,
                self._chat_id,
                kind="send",
                label="send_message(stream_start)",
                action=lambda: _send_preview_message(
                    self._bot, self._chat_id, html_text, plain_text
                ),
            )
            self._message_id = int(getattr(sent, "message_id", 0) or 0) or None
            self._last_sent_plain = plain_text
        else:
            if await self._try_edit_preview_message(html_text, plain_text):
                self._last_sent_plain = plain_text

    async def _try_edit_preview_message(
        self,
        html_text: str,
        plain_text: str,
    ) -> bool:
        try:
            if self._limiter is None:
                await _edit_preview_message(
                    self._bot,
                    self._chat_id,
                    self._message_id,
                    html_text,
                    plain_text,
                )
            else:
                await _run_outbound(
                    self._limiter,
                    self._chat_id,
                    kind="edit",
                    label="edit_message_text(stream)",
                    action=lambda: _edit_preview_message(
                        self._bot,
                        self._chat_id,
                        self._message_id,
                        html_text,
                        plain_text,
                    ),
                )
            return True
        except RetryAfter as e:
            delay = max(float(getattr(e, "retry_after", 1.0) or 1.0), 1.0)
            now = asyncio.get_running_loop().time()
            self._edit_cooldown_until = now + delay
            logger.warning(
                "[telegram] edit_message_text(stream) 命中限流，进入冷却 %.1fs err=%s",
                delay,
                e,
            )
            return False
        except (TimedOut, NetworkError) as e:
            logger.warning("[telegram] edit_message_text(stream) 失败 err=%s", e)
            return False

def _iter_stream_chunks(text: str) -> list[str]:
    if len(text) <= _STREAM_CHUNK_STEP:
        return [text]
    chunks: list[str] = []
    start = 0
    while start < len(text):
        end = min(start + _STREAM_CHUNK_STEP, len(text))
        if end < len(text):
            newline = text.rfind("\n", start, end)
            if newline > start:
                end = newline + 1
        chunks.append(text[start:end])
        start = end
    return chunks


async def _send_preview_message(bot: Bot, chat_id: int, html_text: str, plain_text: str):
    try:
        return await bot.send_message(
            chat_id=chat_id,
            text=html_text,
            parse_mode="HTML",
        )
    except Exception as e:
        if not _is_telegram_html_parse_error(e):
            raise
        logger.warning("[telegram] preview HTML 解析失败，降级纯文本: %s", e)
        return await bot.send_message(chat_id=chat_id, text=plain_text)


async def _edit_preview_message(
    bot: Bot,
    chat_id: int,
    message_id: int | None,
    html_text: str,
    plain_text: str,
) -> None:
    try:
        await bot.edit_message_text(
            chat_id=chat_id,
            message_id=message_id,
            text=html_text,
            parse_mode="HTML",
        )
    except BadRequest as e:
        if _is_telegram_message_not_modified_error(e):
            logger.debug("[telegram] preview edit skipped: %s", e)
            return
        if not _is_telegram_html_parse_error(e):
            raise
        logger.warning("[telegram] preview edit HTML 解析失败，降级纯文本: %s", e)
        await bot.edit_message_text(
            chat_id=chat_id,
            message_id=message_id,
            text=plain_text,
        )
    except Exception as e:
        if not _is_telegram_html_parse_error(e):
            raise
        logger.warning("[telegram] preview edit HTML 解析失败，降级纯文本: %s", e)
        await bot.edit_message_text(
            chat_id=chat_id,
            message_id=message_id,
            text=plain_text,
        )
