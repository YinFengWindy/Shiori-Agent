"""Stable public entry point for the NcatBot QQ channel."""

import asyncio

from core.common.workspace import resolve_ncatbot_dir
from infra.channels.base import AttachmentStore
from infra.channels.group_filter import (
    DefaultGroupFilter,
    GroupMessageFilter,
    QQGroupFilterConfig,
    strip_at_segments,
)

from .compat import (
    download_to_temp as _download_to_temp,
    extract_cq_images as _extract_cq_images,
    is_local as _is_local,
    local_to_base64 as _local_to_base64,
    patch_ncatbot_ws_open_timeout as _patch_ncatbot_ws_open_timeout,
)
from .formatting import (
    CHANNEL as _CHANNEL,
    GROUP_PREFIX as _GROUP_PREFIX,
    _QQTraceLine,
    _QQTraceState,
    compress_tool_line as _compress_tool_line,
    format_tool_intent as _format_tool_intent,
    format_tool_target as _format_tool_target,
    format_tool_trace_lines as _format_tool_trace_lines,
    session_key_for_chat as _session_key_for_chat,
    summarize_tool_result_preview as _summarize_tool_result_preview,
    tool_emoji as _tool_emoji,
    truncate_trace_text as _truncate_trace_text,
)
from .lifecycle import QQChannel

__all__ = ["QQChannel"]
