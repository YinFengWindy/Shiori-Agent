"""Telegram 发送函数的 facade 兼容调用。"""

from __future__ import annotations

from importlib import import_module
from typing import Any

from infra.channels.telegram_utils import (
    send_markdown as _send_markdown_impl,
    send_stream_markdown as _send_stream_markdown_impl,
    send_thinking_block as _send_thinking_block_impl,
)


async def _call_send_markdown(*args: Any, **kwargs: Any):
    facade = import_module("infra.channels.telegram_channel")
    hook = getattr(facade, "send_markdown", _send_markdown_impl)
    return await hook(*args, **kwargs)

async def _call_send_stream_markdown(*args: Any, **kwargs: Any):
    facade = import_module("infra.channels.telegram_channel")
    hook = getattr(facade, "send_stream_markdown", _send_stream_markdown_impl)
    return await hook(*args, **kwargs)


async def _call_send_thinking_block(*args: Any, **kwargs: Any):
    facade = import_module("infra.channels.telegram_channel")
    hook = getattr(facade, "send_thinking_block", _send_thinking_block_impl)
    return await hook(*args, **kwargs)
