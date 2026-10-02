"""原始会话消息查询工具。"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, cast

from shiori_sdk.tools import Tool, ToolResult
from conversation.context_scope import ContextView, session_context_view
from conversation.service import desktop_thread_id
from session.manager.helpers import (
    ROLE_SESSION_PREFIX,
    is_role_session_key,
    role_session_key,
)
from session.store import SessionStore

# 决定检索范围的回合身份：只从执行上下文取，模型传同名参数无效。
_TURN_SCOPE_KEYS = frozenset({"turn_session_key", "role_id", "thread_id"})

_MAX_CONTEXT = 10
_MAX_PREVIEW_LINES = 50


class FetchMessagesTool(Tool):
    name = "fetch_messages"
    context_precedence = _TURN_SCOPE_KEYS
    description = (
        "fetch_messages 根据消息 ID 或 source_ref 读取原始历史消息原文与上下文。\n"
        "这是 recall_memory / search_messages / 记忆注入三条路里唯一可以直接作为最终证据的工具。\n"
        "何时必须调用：回答依赖具体时间、原话、金额、配置值、是否发生过——只要结论需要事实支撑，就在回复前调用此工具。\n"
        "recall_memory 返回 evidence 时优先传 evidence；search_messages 返回 source_ref 时传 source_ref。\n"
        "支持 context 参数扩展前后文，适合还原完整上下文片段。"
    )
    parameters = {
        "type": "object",
        "properties": {
            "ids": {
                "type": "array",
                "items": {"type": "string"},
                "description": "消息 ID 列表，格式如 'telegram:<chat_id>:<message_id>'",
            },
            "source_ref": {
                "type": "string",
                "description": "单个 source_ref，可传 message id 或记忆条目的 source_ref",
            },
            "source_refs": {
                "type": "array",
                "items": {"type": "string"},
                "description": "多个 source_ref，可混合传 message id 与记忆条目的 source_ref",
            },
            "evidence": {
                "type": "array",
                "items": {"type": "object"},
                "description": "recall_memory 返回的 evidence 列表",
            },
            "context": {
                "type": "integer",
                "description": "每条消息前后各扩展的上下文条数（0=仅精确匹配，最大 10，默认 0）",
                "minimum": 0,
                "maximum": _MAX_CONTEXT,
                "default": 0,
            },
        },
    }

    def __init__(self, store: SessionStore, workspace: Path) -> None:
        self._store = store
        self._workspace = workspace

    async def execute(
        self,
        ids: list[str] | None = None,
        source_ref: str | None = None,
        source_refs: list[str] | None = None,
        evidence: list[dict[str, object]] | None = None,
        context: int = 0,
        **kwargs: Any,
    ) -> str:
        clean_ids = _resolve_fetch_ids(
            ids=ids or [],
            source_ref=source_ref,
            source_refs=source_refs or [],
            evidence=evidence or [],
        )
        if not clean_ids:
            return json.dumps(
                {"count": 0, "matched_count": 0, "messages": []}, ensure_ascii=False
            )

        scope = _turn_scope(self._workspace, kwargs)
        ctx = max(0, min(int(context), _MAX_CONTEXT))
        if ctx == 0:
            messages = [
                _to_public_message(m)
                for m in self._store.fetch_by_ids(clean_ids)
                if _visible(m, scope)
            ]
            return json.dumps(
                {
                    "count": len(messages),
                    "matched_count": len(messages),
                    "messages": messages,
                },
                ensure_ascii=False,
            )

        messages = [
            _to_public_message(m)
            for m in self._store.fetch_by_ids_with_context(clean_ids, ctx)
            if _visible(m, scope)
        ]
        matched = sum(1 for m in messages if m.get("in_source_ref"))
        return json.dumps(
            {"count": len(messages), "matched_count": matched, "messages": messages},
            ensure_ascii=False,
        )


class UserContextMessageTool(Tool):
    """把一个消息检索工具固定在某角色的用户上下文里。

    主动类回合（如 drift）不在任何会话里回复，按约定使用用户上下文：这里以
    角色共享会话和桌面会话作为回合身份，可见范围仍由 ``context_scope`` 判定。
    模型传入的同名参数会被覆盖；只包装消息工具，不影响其他工具收到的上下文。
    """

    def __init__(self, wrapped: Tool, role_id: str) -> None:
        self._wrapped = wrapped
        self._scope = {
            "turn_session_key": role_session_key(role_id),
            "role_id": role_id,
            "thread_id": desktop_thread_id(role_id),
        }

    @property
    def name(self) -> str:
        return self._wrapped.name

    @property
    def description(self) -> str:
        return self._wrapped.description

    @property
    def parameters(self) -> dict[str, Any]:
        return self._wrapped.parameters

    async def execute(self, **kwargs: Any) -> str | ToolResult:
        return await self._wrapped.execute(**{**kwargs, **self._scope})


def _turn_scope(
    workspace: Path, context: dict[str, Any]
) -> tuple[str, ContextView] | None:
    """当前回合在角色共享会话里时，返回该会话的键与回合的上下文视图。

    回合身份只取自工具上下文（``turn_session_key`` / ``role_id`` / ``thread_id``，
    见 ``_TURN_SCOPE_KEYS``），模型无法改写。其余回合返回 None，这时无法判定
    上下文，角色共享会话的消息一律不可见。
    """
    session_key = str(context.get("turn_session_key") or "")
    view = session_context_view(
        workspace,
        session_key=session_key,
        role_id=str(context.get("role_id") or ""),
        thread_id=str(context.get("thread_id") or ""),
    )
    return (session_key, view) if view is not None else None


def _visible(message: dict[str, Any], scope: tuple[str, ContextView] | None) -> bool:
    """角色回合只能读到本角色会话里、属于回合所在上下文的消息。"""
    if scope is None:
        return not is_role_session_key(str(message.get("session_key") or ""))
    session_key, view = scope
    return message.get("session_key") == session_key and view.includes(message)


def _resolve_fetch_ids(
    *,
    ids: list[str],
    source_ref: str | None,
    source_refs: list[str],
    evidence: list[dict[str, object]],
) -> list[str]:
    resolved: list[str] = []
    seen: set[str] = set()
    for value in (
        list(ids)
        + ([source_ref] if source_ref else [])
        + list(source_refs)
        + _source_refs_from_evidence(evidence)
    ):
        for item_id in _expand_source_ref(value):
            if item_id not in seen:
                seen.add(item_id)
                resolved.append(item_id)
    return resolved


def _source_refs_from_evidence(evidence: list[dict[str, object]]) -> list[str]:
    values: list[str] = []
    for item in evidence:
        source_ref = str(item.get("source_ref") or "").strip()
        if source_ref:
            values.append(source_ref)
        refs = item.get("refs")
        if isinstance(refs, list):
            for ref in cast(list[object], refs):
                text = str(ref).strip()
                if text:
                    values.append(text)
    return values


def _expand_source_ref(value: str | None) -> list[str]:
    raw = str(value or "").strip()
    if not raw:
        return []
    prefix = raw.split("#", 1)[0].strip()
    if not prefix:
        return []
    try:
        parsed: object = json.loads(prefix)
    except (json.JSONDecodeError, ValueError):
        return [prefix]
    if isinstance(parsed, list):
        values: list[str] = []
        for item in cast(list[object], parsed):
            text = str(item).strip()
            if text:
                values.append(text)
        return values
    if isinstance(parsed, str) and parsed.strip():
        return [parsed.strip()]
    return []


def _to_public_message(message: dict[str, Any]) -> dict[str, Any]:
    keep = {"id", "session_key", "seq", "role", "content", "timestamp", "in_source_ref"}
    return {k: v for k, v in message.items() if k in keep}


class SearchMessagesTool(Tool):
    name = "search_messages"
    context_precedence = _TURN_SCOPE_KEYS
    description = (
        "对原始历史消息做 grep 式搜索，返回命中候选消息的预览和 source_ref。\n"
        "适合查找某个词、句子、文件名、报错、命令、配置项曾出现在哪些消息里——它是文本定位工具。\n"
        "不是记忆检索工具：不负责总结偏好、判断做没做过、回答历史事实。这些问题先用 recall_memory。\n"
        "命中后若需确认上下文或以结果作为证据，必须继续 fetch_messages(source_ref)，预览不能直接作证。\n"
        "recall_memory 返回的摘要读起来像[询问行为]而非[事件本身]时，可同步用此工具补一路 grep 交叉验证。"
    )
    parameters = {
        "type": "object",
        "properties": {
            "query": {"type": "string", "description": "搜索关键词或短语"},
            "session_key": {
                "type": "string",
                "description": "限定 session，如 'telegram:<chat_id>'（可选）",
            },
            "role": {
                "type": "string",
                "enum": ["user", "assistant"],
                "description": "限定发言方（可选）",
            },
            "limit": {
                "type": "integer",
                "description": "最多返回条数，默认 10，最大 50",
                "minimum": 1,
                "maximum": 50,
                "default": 10,
            },
            "offset": {
                "type": "integer",
                "description": "分页偏移量，默认 0；下一页可用返回里的 next_offset",
                "minimum": 0,
                "default": 0,
            },
        },
        "required": ["query"],
    }

    def __init__(self, store: SessionStore, workspace: Path) -> None:
        self._store = store
        self._workspace = workspace

    async def execute(self, query: str, **kwargs: Any) -> str:
        term = (query or "").strip()
        if not term:
            return _empty_search_result(10, 0)

        limit = max(1, min(int(kwargs.get("limit", 10)), 50))
        offset = max(0, int(kwargs.get("offset", 0)))

        scope = _turn_scope(self._workspace, kwargs)
        excluded_prefix: str | None = None
        if scope is None:
            # 判定不了上下文时不碰任何角色共享会话。
            session_key = (kwargs.get("session_key") or "").strip() or None
            if session_key is not None and is_role_session_key(session_key):
                return _empty_search_result(limit, offset)
            thread_ids = None
            excluded_prefix = ROLE_SESSION_PREFIX
        else:
            # 角色回合只搜本角色会话，且只搜回合所在上下文的会话。
            session_key, view = scope
            thread_ids = [
                thread_id
                for thread_id in self._store.session_thread_ids(session_key)
                if view.includes_thread(thread_id)
            ]
        matched, total = self._store.search_messages(
            term,
            session_key=session_key,
            role=(kwargs.get("role") or "").strip() or None,
            limit=limit,
            offset=offset,
            thread_ids=thread_ids,
            excluded_session_prefix=excluded_prefix,
        )
        terms = [t for t in term.split() if t]
        messages = [_build_search_preview(message, terms) for message in matched]
        next_offset = offset + len(messages)
        has_more = next_offset < total
        if not has_more:
            next_offset = None
        return json.dumps(
            {
                "count": len(messages),
                "matched_count": total,
                "limit": limit,
                "offset": offset,
                "has_more": has_more,
                "next_offset": next_offset,
                "messages": messages,
            },
            ensure_ascii=False,
        )


def _empty_search_result(limit: int, offset: int) -> str:
    return json.dumps(
        {
            "count": 0,
            "matched_count": 0,
            "limit": limit,
            "offset": offset,
            "has_more": False,
            "next_offset": None,
            "messages": [],
        },
        ensure_ascii=False,
    )


def _build_search_preview(
    message: dict[str, Any], query_terms: list[str] | None = None
) -> dict[str, Any]:
    content = str(message.get("content", "") or "")
    preview, line_count, truncated = _preview_lines(
        content, max_lines=_MAX_PREVIEW_LINES
    )
    matched_terms = (
        [t for t in query_terms if t.lower() in content.lower()] if query_terms else []
    )
    result: dict[str, Any] = {
        "id": str(message.get("id", "") or ""),
        "source_ref": str(message.get("id", "") or ""),
        "session_key": str(message.get("session_key", "") or ""),
        "seq": int(message.get("seq", 0) or 0),
        "role": str(message.get("role", "") or ""),
        "timestamp": str(message.get("timestamp", "") or ""),
        "matched_terms": matched_terms,
        "preview": preview,
        "preview_line_count": min(line_count, _MAX_PREVIEW_LINES),
        "total_line_count": line_count,
        "truncated": truncated,
    }
    return result


def _preview_lines(content: str, *, max_lines: int) -> tuple[str, int, bool]:
    lines = content.splitlines()
    if not lines:
        return content[:0], 0, False
    selected = lines[:max_lines]
    truncated = len(lines) > max_lines
    preview = "\n".join(selected)
    if truncated:
        preview += f"\n...[已截断，剩余 {len(lines) - max_lines} 行]"
    return preview, len(lines), truncated
