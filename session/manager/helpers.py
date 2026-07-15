"""Session 历史投影与迁移的共享纯辅助函数。"""

from __future__ import annotations

import base64
import logging
import mimetypes
import re
from datetime import datetime
from pathlib import Path
from typing import Any

from agent.prompting import (
    PromptSectionRender,
    build_context_frame_content,
    build_context_frame_message,
)

logger = logging.getLogger(__name__)

_TOOL_RESULT_CHAR_BUDGET = 10000
_PROACTIVE_HISTORY_CHAR_BUDGET = 360
_PROACTIVE_META_HISTORY_CHAR_BUDGET = 1200
_ROLE_SESSION_PREFIX = "role:"


def _timestamp_at_or_before(value: str, cutoff: str) -> bool:
    """Compares migration timestamps while tolerating legacy malformed values."""

    try:
        return datetime.fromisoformat(value) <= datetime.fromisoformat(cutoff)
    except (TypeError, ValueError):
        return bool(value and value <= cutoff)


def _truncate_tool_result(content: object) -> str:
    text = content if isinstance(content, str) else str(content)
    if len(text) <= _TOOL_RESULT_CHAR_BUDGET:
        return text
    omitted = len(text) - _TOOL_RESULT_CHAR_BUDGET
    while True:
        marker = f"…{omitted} chars truncated…"
        keep = max(0, _TOOL_RESULT_CHAR_BUDGET - len(marker))
        actual_omitted = len(text) - keep
        if actual_omitted == omitted:
            break
        omitted = actual_omitted
    head = keep // 2
    tail = keep - head
    truncated = text[:head] + marker + (text[-tail:] if tail else "")
    return f"Total output lines: {len(text.splitlines())}\n\n{truncated}"


def _append_proactive_meta(content: str, msg: dict[str, Any]) -> str:
    """Expose source trace and state tag back to the model without changing user-visible text."""
    if not msg.get("proactive"):
        return content
    meta_lines: list[str] = []
    state_tag = str(msg.get("state_summary_tag", "") or "").strip()
    if state_tag and state_tag != "none":
        meta_lines.append(f"state_summary_tag={state_tag}")
    source_refs = msg.get("source_refs") or []
    if isinstance(source_refs, list) and source_refs:
        meta_lines.append("sources:")
        for raw in source_refs[:1]:
            if not isinstance(raw, dict):
                continue
            parts = [
                str(raw.get("source_name", "") or "").strip(),
                str(raw.get("title", "") or "").strip(),
                str(raw.get("url", "") or "").strip(),
            ]
            meta_lines.append("- " + " | ".join(p for p in parts if p))
    if not meta_lines:
        return content
    return f"{content}\n\n[proactive_meta]\n" + "\n".join(meta_lines)


def _build_proactive_history_messages(
    content: str,
    msg: dict[str, Any],
) -> list[dict[str, str]]:
    preview = _truncate_text(content, _PROACTIVE_HISTORY_CHAR_BUDGET)
    messages = [
        {
            "role": "assistant",
            "content": preview,
        }
    ]
    meta = _append_proactive_meta("", msg).strip()
    context = (
        "上一条 assistant 消息是系统主动推送。"
        "该信息仅用于理解会话来源，不是用户陈述。"
    )
    if meta:
        context += (
            "\n以下 metadata 仅用于理解用户后续指代，不是用户陈述。\n"
            + _truncate_text(meta, _PROACTIVE_META_HISTORY_CHAR_BUDGET)
        )
    frame = build_context_frame_message(
        build_context_frame_content(
            [
                PromptSectionRender(
                    name="recent_proactive_message_meta",
                    content=context,
                    is_static=False,
                )
            ]
        )
    )
    messages.append(frame)
    return messages


def _truncate_text(text: str, limit: int) -> str:
    if len(text) <= limit:
        return text
    return text[:limit].rstrip() + f"…（截断 {len(text) - limit} 字）"


def _rebuild_user_content(text: str, media_paths: list[str]) -> "str | list[dict]":
    """重建带附件的用户消息。图片内联 base64；非图片文件保留路径引用供 agent 调用 read_file。"""
    images = []
    file_refs = []
    for path in media_paths:
        p = Path(path)
        mime, _ = mimetypes.guess_type(p)
        if mime and mime.startswith("image/") and p.is_file():
            try:
                b64 = base64.b64encode(p.read_bytes()).decode()
                images.append(
                    {
                        "type": "image_url",
                        "image_url": {"url": f"data:{mime};base64,{b64}"},
                    }
                )
            except Exception:
                file_refs.append(f"[图片（读取失败）: {p.name}]")
        else:
            if p.is_file():
                file_refs.append(f"[文件: {path}]")
            else:
                file_refs.append(f"[文件（已失效）: {p.name}]")

    prefix = "\n".join(file_refs) + "\n" if file_refs else ""
    combined_text = (prefix + text).strip()

    if not images:
        return combined_text
    return images + [{"type": "text", "text": combined_text}]


def _align_to_user_boundary(messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
    for i, m in enumerate(messages):
        if m.get("role") == "user" or (
            m.get("role") == "assistant" and m.get("proactive")
        ):
            return messages[i:]
    return []


def _safe_filename(key: str) -> str:
    """Convert a session key to a safe filename."""
    return re.sub(r"[^\w\-]", "_", key)
