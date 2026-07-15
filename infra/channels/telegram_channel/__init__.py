"""Telegram channel 的稳定公共入口。"""

import asyncio
import logging

from telegram import BotCommand, Update
from telegram.constants import ChatAction
from telegram.error import Conflict, NetworkError, TelegramError, TimedOut
from telegram.ext import (
    Application,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

from infra.channels.telegram_utils import (
    TelegramLiveEditQueue,
    TelegramLiveTextMessage,
    TelegramOutboundLimiter,
    TelegramStreamMessage,
    send_markdown,
    send_stream_markdown,
    send_thinking_block,
)

from .formatting import (
    _CHANNEL,
    _LIVE_STREAM_MIN_CHARS,
    _LIVE_STREAM_MIN_INTERVAL_S,
    _REPLY_LIVE_TAIL,
    _SEEN_MSG_MAXSIZE,
    _THINKING_LIVE_TAIL,
    _TOOL_LIVE_TAIL,
    _TOOL_PREVIEW_LIMIT,
    _ToolLiveLine,
    _build_inbound_text_with_reply,
    _clip_inline,
    _format_tool_intent,
    _format_tool_live,
    _format_tool_target,
    _format_turn_live,
    _live_buffer_len,
    _stringify_tool_value,
    _tail_text,
    _tool_emoji,
)
from .lifecycle import TelegramChannel

logger = logging.getLogger("infra.channels.telegram_channel")
