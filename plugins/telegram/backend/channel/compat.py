"""Telegram 发送函数的 facade 兼容调用。

渠道包在宿主里以内核生成的包名加载（``akasic_plugin_<ns>_telegram.channel``），
测试里则以 ``plugins.telegram.backend.channel`` 导入，所以按本包的实际包名
查找 facade，而不是写死模块路径。
"""

from __future__ import annotations

from importlib import import_module
from types import ModuleType
from typing import Any

from ..utils import (
    send_markdown as _send_markdown_impl,
    send_stream_markdown as _send_stream_markdown_impl,
    send_thinking_block as _send_thinking_block_impl,
)


def _facade() -> ModuleType:
    assert __package__, "compat 必须作为渠道包的子模块加载"
    return import_module(__package__)


async def _call_send_markdown(*args: Any, **kwargs: Any):
    hook = getattr(_facade(), "send_markdown", _send_markdown_impl)
    return await hook(*args, **kwargs)


async def _call_send_stream_markdown(*args: Any, **kwargs: Any):
    hook = getattr(_facade(), "send_stream_markdown", _send_stream_markdown_impl)
    return await hook(*args, **kwargs)


async def _call_send_thinking_block(*args: Any, **kwargs: Any):
    hook = getattr(_facade(), "send_thinking_block", _send_thinking_block_impl)
    return await hook(*args, **kwargs)
