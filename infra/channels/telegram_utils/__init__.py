"""Telegram 发送、流式编辑与 Markdown 渲染工具的稳定 facade。"""

import asyncio

from telegram import Bot, MessageEntity as TgEntity
from telegram.error import BadRequest, NetworkError, RetryAfter, TimedOut
from telegramify_markdown.converter import convert_with_segments
from telegramify_markdown.entity import MessageEntity, split_entities

from .limiter import (
    TelegramOutboundLimiter,
    _run_outbound,
    _send_with_retry,
    _send_with_retry_result,
)
from .live_edit import (
    TelegramLiveEditQueue,
    TelegramLiveTextMessage,
    _clip_live_text,
    _edit_live_message,
    _send_live_message,
)
from .rendering import (
    _append_preview_part,
    _is_telegram_html_parse_error,
    _is_telegram_message_not_modified_error,
    _prepare_preview_markdown,
    _render_inline,
    _render_inline_match,
    _render_preview_blocks,
    render_telegram_preview_html,
)
from .sending import (
    _serialize_entities,
    _split_text,
    _split_thinking,
    _strip_chunk,
    _utf16_cut,
    send_markdown,
    send_stream_markdown,
    send_thinking_block,
)
from .streaming import (
    TelegramStreamMessage,
    _edit_preview_message,
    _iter_stream_chunks,
    _ring_tail,
    _send_preview_message,
)

__all__ = [
    "TelegramLiveEditQueue",
    "TelegramLiveTextMessage",
    "TelegramOutboundLimiter",
    "TelegramStreamMessage",
    "render_telegram_preview_html",
    "send_markdown",
    "send_stream_markdown",
    "send_thinking_block",
]
