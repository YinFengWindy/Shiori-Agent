"""Session 历史投影与迁移的共享纯辅助函数。"""

from __future__ import annotations

import base64
import logging
import mimetypes
import re
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from core.common.text import truncate_text
from agent.prompting import build_context_frame_content, build_context_frame_message
from shiori_sdk.prompting import PromptSectionRender

logger = logging.getLogger(__name__)

_TOOL_RESULT_CHAR_BUDGET = 10000
_PROACTIVE_HISTORY_CHAR_BUDGET = 360
_PROACTIVE_META_HISTORY_CHAR_BUDGET = 1200
# Every role's shared session key starts with this.
ROLE_SESSION_PREFIX = "role:"
_ROLE_SESSION_PREFIX = ROLE_SESSION_PREFIX


def role_session_key(role_id: str) -> str:
    """The key of one role's shared session, which holds all of its threads."""
    clean_role_id = str(role_id).strip()
    if not clean_role_id:
        raise ValueError("role_id 不能为空")
    return f"{_ROLE_SESSION_PREFIX}{clean_role_id}"


def is_role_session_key(key: str) -> bool:
    """Whether ``key`` names a role's shared session."""
    return key.startswith(_ROLE_SESSION_PREFIX) and len(key) > len(_ROLE_SESSION_PREFIX)


def role_id_from_session_key(key: str) -> str:
    """The role that owns shared session ``key``; "" when ``key`` is not one."""
    clean_key = str(key or "").strip()
    if not clean_key.startswith(_ROLE_SESSION_PREFIX):
        return ""
    return clean_key.removeprefix(_ROLE_SESSION_PREFIX).strip()


def truncate_tool_result(content: object, limit: int = _TOOL_RESULT_CHAR_BUDGET) -> str:
    """Keep head and tail of a tool result within ``limit`` chars for model input.

    Model history and working-summary sources share this rule so the summary never
    sees more tool output than the model did.
    """
    text = content if isinstance(content, str) else str(content)
    if len(text) <= limit:
        return text
    omitted = len(text) - limit
    while True:
        marker = f"…{omitted} chars truncated…"
        keep = max(0, limit - len(marker))
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
    preview = truncate_text(content, _PROACTIVE_HISTORY_CHAR_BUDGET)
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
            + truncate_text(meta, _PROACTIVE_META_HISTORY_CHAR_BUDGET)
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


def starts_turn(message: Mapping[str, Any]) -> bool:
    """原始消息是否是一轮的起点：user 消息或主动消息。

    历史窗口对齐到完整 turn、按轮切分历史都以此为准。
    """
    role = message.get("role")
    return role == "user" or (role == "assistant" and bool(message.get("proactive")))


def _align_to_user_boundary(messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
    for i, m in enumerate(messages):
        if starts_turn(m):
            return messages[i:]
    return []


def _safe_filename(key: str) -> str:
    """Convert a session key to a safe filename."""
    return re.sub(r"[^\w\-]", "_", key)
