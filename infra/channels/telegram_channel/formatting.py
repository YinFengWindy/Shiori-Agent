"""Telegram live 文本与入站回复上下文格式化。"""

from __future__ import annotations

import html
import json
from dataclasses import dataclass
from typing import Any

from infra.channels.reply_context import build_inbound_text_with_reply_context


_CHANNEL = "telegram"
_SEEN_MSG_MAXSIZE = 500  # 滑动窗口大小，防止内存无限增长
_THINKING_LIVE_TAIL = 1400
_TOOL_LIVE_TAIL = 1000
_REPLY_LIVE_TAIL = 1100
_TOOL_PREVIEW_LIMIT = 80
_LIVE_STREAM_MIN_INTERVAL_S = 2.5
_LIVE_STREAM_MIN_CHARS = 200


@dataclass
class _ToolLiveLine:
    call_id: str
    tool_name: str
    intent: str
    target: str
    status: str = "running"


def _format_turn_live(
    lines: list[_ToolLiveLine],
    reply: str,
    thinking: str,
    *,
    terminal: bool = False,
) -> tuple[str, str]:
    blocks: list[str] = []
    html_blocks: list[str] = []
    thinking_body = _tail_text(thinking.strip(), _THINKING_LIVE_TAIL)
    if thinking_body:
        thinking_text = f"思考过程\n{thinking_body}"
        blocks.append(thinking_text)
        html_blocks.append(f"<blockquote>{html.escape(thinking_text)}</blockquote>")
    if lines:
        tool_text = _tail_text(_format_tool_live(lines), _TOOL_LIVE_TAIL)
        blocks.append(tool_text)
        html_blocks.append(f"<pre>{html.escape(tool_text)}</pre>")
    reply_body = _tail_text(reply.strip(), _REPLY_LIVE_TAIL)
    if reply_body and not terminal:
        reply_text = f"临时回复\n{reply_body}"
        blocks.append(reply_text)
        html_blocks.append(f"<b>临时回复</b>\n{html.escape(reply_body)}")
    if terminal and not blocks:
        return "本轮预览完成", "<pre>本轮预览完成</pre>"
    return "\n\n".join(blocks), "\n\n".join(html_blocks)


def _format_tool_live(lines: list[_ToolLiveLine]) -> str:
    shown = lines[-12:]
    rows = ["工具调用"]
    hidden = len(lines) - len(shown)
    if hidden > 0:
        rows.append(f"... {hidden} more")
    for line in shown:
        status = "..."
        if line.status == "done":
            status = "✅"
        elif line.status == "error":
            status = "✗"
        target = f" {line.target}" if line.target else ""
        rows.append(
            f"{_tool_emoji(line.tool_name)} {_clip_inline(line.tool_name, 32)}: "
            f"{line.intent}{target} {status}"
        )
    if lines and all(line.status != "running" for line in lines):
        rows.append(f"Done · {len(lines)} tools")
    return "\n".join(rows)


def _format_tool_intent(arguments: dict[str, object]) -> str:
    value = arguments.get("description")
    if value is None or value == "":
        return ""
    return _clip_inline(_stringify_tool_value(value), _TOOL_PREVIEW_LIMIT)


def _format_tool_target(arguments: dict[str, object]) -> str:
    if not arguments:
        return ""
    primary_keys = (
        "cmd",
        "command",
        "query",
        "url",
        "path",
        "file",
        "text",
        "content",
        "prompt",
        "name",
    )
    for key in primary_keys:
        value = arguments.get(key)
        if value is not None and value != "":
            return f"\"{_clip_inline(_stringify_tool_value(value), _TOOL_PREVIEW_LIMIT)}\""
    return ""


def _stringify_tool_value(value: object) -> str:
    if isinstance(value, str):
        return value
    try:
        return json.dumps(value, ensure_ascii=False, default=str)
    except TypeError:
        return str(value)


def _clip_inline(text: str, limit: int) -> str:
    plain = " ".join(str(text).split())
    if len(plain) <= limit:
        return plain
    if limit <= 3:
        return plain[:limit]
    return plain[: limit - 3] + "..."


def _tail_text(text: str, limit: int) -> str:
    if len(text) <= limit:
        return text
    return "..." + text[-(limit - 3):]


def _live_buffer_len(reply: str, thinking: str) -> int:
    return len(reply) + len(thinking)


def _tool_emoji(tool_name: str) -> str:
    name = tool_name.lower()
    if name.startswith("mcp"):
        return "📡"
    if "search" in name:
        return "🔍"
    if "web" in name or "url" in name:
        return "🌐"
    if "file" in name or "read" in name:
        return "📄"
    if "write" in name or "save" in name:
        return "💾"
    if "shell" in name or "exec" in name:
        return "⚙"
    return "🔧"


def _build_inbound_text_with_reply(
    user_text: str,
    reply_msg,
) -> tuple[str, dict[str, str | int]]:
    """将 Telegram 的 reply 上下文合并进入站文本，避免 agent 丢失引用信息。"""
    text = (user_text or "").strip()
    if not reply_msg:
        return text, {}

    reply_text = (reply_msg.text or reply_msg.caption or "").strip()
    if not reply_text:
        # 被回复消息无文字：若含图片则用占位符，否则只保留元信息
        if getattr(reply_msg, "photo", None):
            reply_text = "[图片]"
        else:
            return text, {"reply_to_message_id": int(reply_msg.message_id)}

    reply_sender = ""
    from_user = getattr(reply_msg, "from_user", None)
    if from_user:
        reply_sender = from_user.username or str(from_user.id)
    sender_label = f"@{reply_sender}" if reply_sender else "未知发送者"

    merged = build_inbound_text_with_reply_context(
        user_text=text,
        reply_text=reply_text,
        reply_sender=sender_label,
    )
    return merged, {
        "reply_to_message_id": int(reply_msg.message_id),
        "reply_to_sender": sender_label,
    }
