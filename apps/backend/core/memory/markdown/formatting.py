"""Markdown memory consolidation 的纯格式化与窗口辅助逻辑。"""

from __future__ import annotations

import hashlib
import json
import re
from typing import TYPE_CHECKING, Any

from shiori_sdk.json import load_json_object_loose
from shiori_sdk.prompting import is_context_frame
from conversation.context_scope import (
    ContextView,
    UserContextThreads,
    belongs_to_user,
    in_user_context,
    stored_message_source,
)
from session.manager.helpers import role_id_from_session_key
from session.manager.models import consolidation_cursor
from session.store.common import ContextScope

from .contracts import ConsolidationSegments, ConsolidationWindow

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


def _window_candidates(
    session, views: tuple[ContextView, ...]
) -> tuple[list[int], list[int]]:
    """整理窗口的候选位置：参与计数的全部消息，以及其中尚未整理的消息。

    ``views`` 为空时是整个会话与 ``last_consolidated``；否则只数这些上下文的消息，
    每条消息按它所属上下文自己的游标判断是否已整理。
    """
    messages = session.messages
    if not views:
        members = list(range(len(messages)))
        return members, members[int(session.last_consolidated) :]
    cursors = [(view, consolidation_cursor(session, view.scope)) for view in views]
    members = [
        index
        for index, message in enumerate(messages)
        if any(view.includes(message) for view in views)
    ]
    pending = [
        index
        for index in members
        if any(
            index >= cursor and view.includes(messages[index])
            for view, cursor in cursors
        )
    ]
    return members, pending


def _select_consolidation_window(
    session,
    *,
    keep_count: int,
    consolidation_min_new_messages: int,
    archive_all: bool,
    force: bool = False,
    through_index: int | None = None,
    views: tuple[ContextView, ...] = (),
) -> ConsolidationWindow | None:
    """选出这次要整理的消息窗口；没有该整理的消息时返回 None。

    ``views`` 为空表示会话只有一段对话（非角色会话），从 ``last_consolidated`` 起
    整理整个会话。角色会话给出要推进的上下文（#523）：窗口只含这些上下文在各自
    游标之后的消息，保留的“最后 keep_count 条”与最小批量也只数这些上下文的消息，
    另一类上下文的消息再多也不影响；平时每次只给一类；archive_all 与不带 scope 的全量
    force 两类一起整理。
    """
    messages = session.messages
    total_messages = len(messages)
    scopes: tuple[ContextScope, ...] = tuple(view.scope for view in views)
    if archive_all:
        return ConsolidationWindow(
            old_messages=list(messages),
            keep_count=0,
            consolidate_up_to=total_messages,
            scopes=scopes,
        )

    members, pending = _window_candidates(session, views)
    if not pending:
        return None

    if through_index is not None:
        if not 0 <= through_index <= total_messages:
            raise ValueError("记忆前置范围超出会话消息")
        consolidate_up_to = through_index
    elif force:
        consolidate_up_to = total_messages
    else:
        if len(members) <= keep_count:
            return None
        consolidate_up_to = (
            members[-keep_count] if 0 < keep_count < len(members) else total_messages
        )
    # Never advance the cursor into the middle of a tool exchange. A tool
    # result belongs to the assistant tool-call message immediately before it.
    old_indices = [index for index in pending if index < consolidate_up_to]
    while old_indices and str(messages[old_indices[-1]].get("role") or "").lower() == (
        "tool"
    ):
        consolidate_up_to = old_indices.pop()
    if not old_indices:
        return None
    if (
        not force
        and through_index is None
        and len(old_indices) < max(1, int(consolidation_min_new_messages))
    ):
        return None
    return ConsolidationWindow(
        old_messages=[messages[index] for index in old_indices],
        keep_count=0 if force or len(members) <= keep_count else keep_count,
        consolidate_up_to=consolidate_up_to,
        scopes=scopes,
    )


def split_consolidation_window(
    window: ConsolidationWindow, user_threads: UserContextThreads | None
) -> ConsolidationSegments:
    """把整理窗口按 ``belongs_to_user`` 拆成用户本人段与外部段。

    ``user_threads`` 为 None 表示会话没有上下文划分（非角色共享会话），整段都属于
    用户本人。
    """
    if user_threads is None:
        return ConsolidationSegments(
            user_messages=list(window.old_messages), external_messages=[]
        )
    user_messages: list[dict] = []
    external_messages: list[dict] = []
    for message in window.old_messages:
        if belongs_to_user(message, user_threads):
            user_messages.append(message)
        else:
            external_messages.append(message)
    return ConsolidationSegments(
        user_messages=user_messages, external_messages=external_messages
    )


def build_consolidation_source_ref(messages: list[dict]) -> str:
    """返回参与本次整理的消息 ID 的 JSON 列表。
    缺失 id 的消息（迁移前的历史脏数据）直接跳过。
    """
    ids = [
        str(msg["id"])
        for msg in messages
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


def _session_role_id(session: object) -> str:
    """会话所属的角色 ID：元数据里记录的，没有时取角色共享会话键里的；都没有为空串。"""
    metadata = getattr(session, "metadata", {})
    role_id = (
        str(metadata.get("role_id") or "").strip() if isinstance(metadata, dict) else ""
    )
    return role_id or role_id_from_session_key(str(getattr(session, "key", "") or ""))


def _session_role_runtime_config(session: object) -> dict[str, Any]:
    metadata = getattr(session, "metadata", None)
    if not isinstance(metadata, dict):
        return {}
    config = metadata.get("role_runtime_config")
    return config if isinstance(config, dict) else {}


def is_nsfw_memory_enabled_session(session: object) -> bool:
    """会话所属角色是否开启了 NSFW 记忆（整理时对亲密内容做抽象化）。"""
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


def _speaker_label(message: dict, user_threads: UserContextThreads | None) -> str:
    """整理输入里的说话人标记；用户本人在外部会话（群聊）的发言带上群名。"""
    role = str(message.get("role", "")).upper()
    if user_threads is None or in_user_context(message, user_threads):
        return role
    group_name = stored_message_source(message).group_name
    return f"{role}（在群「{group_name}」里）" if group_name else f"{role}（在群聊里）"


def format_conversation_for_consolidation(
    old_messages: list[dict],
    *,
    nsfw_memory_enabled: bool = False,
    user_threads: UserContextThreads | None = None,
) -> str:
    """把用户本人段格式化成整理输入。

    ``user_threads`` 给出时，不在用户上下文会话里的消息（用户在群里的发言）标注
    群名；为 None 时不标注。
    """
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
        role = _speaker_label(message, user_threads)
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


def append_entries_to_journal(
    profile_maint: "MarkdownMemoryStore",
    entries: list[str],
    source_ref: str,
) -> None:
    """把带 ``[YYYY-MM-DD`` 前缀的事件条目按日期幂等追加到日记；无日期的跳过。"""
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
