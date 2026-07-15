"""Markdown memory consolidation 的纯格式化与窗口辅助逻辑。"""

from __future__ import annotations

import hashlib
import json
import re
from typing import TYPE_CHECKING, Any

from agent.llm_json import load_json_object_loose
from agent.prompting import is_context_frame

from .contracts import _ConsolidationWindow

if TYPE_CHECKING:
    from .runtime import MarkdownMemoryStore

_ALLOWED_PENDING_TAGS = frozenset(
    {
        "identity",
        "preference",
        "key_info",
        "health_long_term",
        "requested_memory",
        "correction",
    }
)


def _format_pending_items(raw_items) -> str:
    """Normalize LLM pending_items into markdown bullets accepted by PENDING.md."""
    if not isinstance(raw_items, list):
        return ""

    lines = []
    seen = set()
    for item in raw_items:
        if not isinstance(item, dict):
            continue
        tag = str(item.get("tag", "")).strip().lower()
        content = str(item.get("content", "")).strip()
        if tag not in _ALLOWED_PENDING_TAGS or not content:
            continue
        line = f"- [{tag}] {content}"
        if line in seen:
            continue
        seen.add(line)
        lines.append(line)
    return "\n".join(lines)


def _parse_consolidation_payload(text: str) -> dict | None:
    return load_json_object_loose(text)


def _format_consolidation_error(exc: BaseException) -> str:
    message = str(exc).strip()
    if message:
        return f"{type(exc).__name__}: {message}"
    return type(exc).__name__

def _select_consolidation_window(
    session,
    *,
    keep_count: int,
    consolidation_min_new_messages: int,
    archive_all: bool,
    force: bool = False,
) -> _ConsolidationWindow | None:
    total_messages = len(session.messages)
    if archive_all:
        return _ConsolidationWindow(
            old_messages=list(session.messages),
            keep_count=0,
            consolidate_up_to=total_messages,
        )

    if total_messages - session.last_consolidated <= 0:
        return None

    if force:
        consolidate_up_to = total_messages
    else:
        if total_messages <= keep_count:
            return None
        consolidate_up_to = total_messages - keep_count
    old_messages = session.messages[session.last_consolidated : consolidate_up_to]
    if not old_messages:
        return None
    if not force and len(old_messages) < max(1, int(consolidation_min_new_messages)):
        return None
    return _ConsolidationWindow(
        old_messages=old_messages,
        keep_count=0 if force else keep_count,
        consolidate_up_to=consolidate_up_to,
    )


def _build_consolidation_source_ref(window: _ConsolidationWindow) -> str:
    """返回本次 consolidation 窗口内所有消息 ID 的 JSON 列表。
    缺失 id 的消息（迁移前的历史脏数据）直接跳过。
    """
    ids = [
        str(msg["id"])
        for msg in window.old_messages
        if msg.get("id") and not _is_context_frame_message(msg)
    ]
    return json.dumps(ids, ensure_ascii=False)


def _build_entry_source_ref(base_source_ref: str, entry: str) -> str:
    """为单条 history_entry 生成稳定子键，避免同窗口多条写入互相覆盖。"""
    text = (entry or "").strip()
    digest = hashlib.sha1(text.encode("utf-8")).hexdigest()[:12] if text else "empty"
    return f"{base_source_ref}#h:{digest}"


_NSFW_MEMORY_EXPLICIT_RE = re.compile(
    r"(做爱|性爱|性行为|插入|抽插|高潮|射精|口交|乳交|内射|子宫|阴道|阴茎|肉棒|龟头|私处|下体)",
    re.I,
)
_NSFW_MEMORY_AFFECTION_RE = re.compile(
    r"(亲吻|接吻|亲你|抱住|拥抱|搂住|抚摸|摸你的|贴着|依偎|窝进)",
    re.I,
)
_NSFW_MEMORY_LOVE_RE = re.compile(r"(爱你|喜欢你|想你|老婆|老公)", re.I)
_NSFW_MEMORY_IMAGE_RE = re.compile(r"(NSFW|实景图|来张图|配图|图片|照片)", re.I)
_NSFW_MEMORY_DEPENDENCY_RE = re.compile(
    r"(抱紧我|别放开|别离开|依赖|离不开|吃醋|占有欲)",
    re.I,
)
_NSFW_MEMORY_SHY_RE = re.compile(r"(害羞|脸红|耳尖|轻哼|别误会|嘴硬)", re.I)


def _session_role_runtime_config(session: object) -> dict[str, Any]:
    metadata = getattr(session, "metadata", None)
    if not isinstance(metadata, dict):
        return {}
    config = metadata.get("role_runtime_config")
    return config if isinstance(config, dict) else {}


def _is_nsfw_memory_enabled_session(session: object) -> bool:
    return bool(_session_role_runtime_config(session).get("nsfw_memory_enabled"))


def _dedupe_semantic_items(items: list[str]) -> list[str]:
    seen: set[str] = set()
    ordered: list[str] = []
    for item in items:
        clean = str(item or "").strip()
        if not clean or clean in seen:
            continue
        seen.add(clean)
        ordered.append(clean)
    return ordered


def _abstract_nsfw_memory_content(role: str, content: str) -> str:
    text = str(content or "").strip()
    if not text:
        return ""
    explicit = bool(_NSFW_MEMORY_EXPLICIT_RE.search(text))
    affection = bool(_NSFW_MEMORY_AFFECTION_RE.search(text))
    romantic = bool(_NSFW_MEMORY_LOVE_RE.search(text))
    dependency = bool(_NSFW_MEMORY_DEPENDENCY_RE.search(text))
    shy = bool(_NSFW_MEMORY_SHY_RE.search(text))
    lowered = text.lower()
    image_request = bool(_NSFW_MEMORY_IMAGE_RE.search(text)) and (
        explicit or affection or romantic or "nsfw" in lowered or "实景" in text
    )
    if not any((explicit, affection, romantic, dependency, shy, image_request)):
        return text

    summary: list[str] = []
    if role == "user":
        if romantic:
            summary.append("表达爱意与依恋")
        if explicit:
            summary.append("主动推进更高强度的亲密互动")
        elif affection:
            summary.append("寻求身体上的亲近与安抚")
        if image_request:
            summary.append("请求亲密场景配图")
        if dependency:
            summary.append("偏好更黏连、被回应的亲密相处")
        if not summary:
            summary.append("描述了亲密互动相关需求")
        return "；".join(_dedupe_semantic_items(summary))

    if romantic:
        summary.append("表达爱意与依恋")
    if explicit:
        summary.append("接受并回应亲密互动")
    elif affection:
        summary.append("回应身体上的亲近与安抚")
    if dependency or shy:
        summary.append("表现出害羞、依赖与占有欲倾向")
    if not summary:
        summary.append("回应了亲密互动")
    return "；".join(_dedupe_semantic_items(summary))


def _normalize_memory_content(
    message: dict,
    *,
    nsfw_memory_enabled: bool,
) -> str:
    content = str(message.get("content") or "").strip()
    if not content:
        return ""
    if not nsfw_memory_enabled:
        return content
    role = str(message.get("role") or "").lower()
    if role not in {"user", "assistant"}:
        return content
    return _abstract_nsfw_memory_content(role, content)


def _format_conversation_for_consolidation(
    old_messages: list[dict],
    *,
    nsfw_memory_enabled: bool = False,
) -> str:
    lines = []
    for message in old_messages:
        if _is_context_frame_message(message):
            continue
        if message.get("role") == "tool":
            continue
        if message.get("role") == "assistant" and message.get("proactive"):
            continue
        content = _normalize_memory_content(
            message,
            nsfw_memory_enabled=nsfw_memory_enabled,
        )
        if not content:
            continue
        role = str(message.get("role", "")).upper()
        ts = str(message.get("timestamp", "?"))[:16]
        lines.append(f"[{ts}] {role}: {content}")
    return "\n".join(lines)


def _select_recent_history_entries(history_text: str, *, limit: int = 3) -> list[str]:
    if not history_text.strip() or limit <= 0:
        return []
    chunks = re.split(r"\n\s*\n+", history_text.strip())
    entries = [chunk.strip() for chunk in chunks if chunk.strip()]
    return entries[-limit:]


def _coerce_history_text(value: object) -> str:
    if isinstance(value, str):
        return value
    return ""


_DATE_PREFIX_RE = re.compile(r"^\[(\d{4}-\d{2}-\d{2})")


def _append_entries_to_journal(
    profile_maint: "MarkdownMemoryStore",
    entries: list[str],
    source_ref: str,
) -> None:
    by_date: dict[str, list[str]] = {}
    for entry in entries:
        m = _DATE_PREFIX_RE.match(entry)
        if not m:
            continue
        by_date.setdefault(m.group(1), []).append(entry)
    for date_str, date_entries in by_date.items():
        combined = "\n".join(date_entries)
        profile_maint.append_journal(
            date_str, combined, source_ref=source_ref, kind=f"journal:{date_str}"
        )


def _coerce_emotional_weight(value: object) -> int:
    if value is None or value == "":
        return 0
    if not isinstance(value, str | int | float):
        return 0
    try:
        return max(0, min(10, int(value)))
    except (TypeError, ValueError):
        return 0


def _normalize_history_entries(
    raw_entries: object,
    fallback_entry: object = None,
) -> list[tuple[str, int]]:
    entries: list[tuple[str, int]] = []
    seen: set[str] = set()
    candidates: list[object] = []
    if isinstance(raw_entries, list):
        candidates.extend(raw_entries)
    elif raw_entries is not None:
        candidates.append(raw_entries)
    if fallback_entry is not None and not isinstance(raw_entries, list):
        candidates.append(fallback_entry)
    for item in candidates:
        if isinstance(item, str):
            summary = item.strip()
            emotional_weight = 0
        elif isinstance(item, dict):
            summary = str(item.get("summary") or "").strip()
            emotional_weight = _coerce_emotional_weight(item.get("emotional_weight"))
        else:
            continue
        if not summary or summary in seen:
            continue
        seen.add(summary)
        entries.append((summary, emotional_weight))
    return entries

def _message_time(message: dict) -> str:
    return str(message.get("timestamp") or "").strip()


def _is_context_frame_message(message: dict) -> bool:
    content = str(message.get("content") or "")
    return is_context_frame(content)


def _is_memory_maintenance_assistant_message(message: dict) -> bool:
    role = str(message.get("role") or "").lower()
    if role != "assistant":
        return False
    tools_used = message.get("tools_used") or []
    if not isinstance(tools_used, list):
        return False
    return "memorize" in {str(item).strip() for item in tools_used if str(item).strip()}
