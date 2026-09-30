"""Session 数据模型。"""

from __future__ import annotations

import json
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from core.common.message_source import MessageSource, with_message_source
from session.store.common import CONTEXT_SCOPES, ContextScope

from .helpers import (
    _align_to_user_boundary,
    is_role_session_key,
    _append_proactive_meta,
    _build_proactive_history_messages,
    _rebuild_user_content,
    _truncate_tool_result,
    starts_turn,
)

INTERRUPTED_TURN_METADATA_KEY = "interrupted_turn"

# Decides whether one raw session message is visible to a history read.
HistoryFilter = Callable[[Mapping[str, Any]], bool]


def whole_session(message: Mapping[str, Any]) -> bool:
    """History filter for readers that deliberately span every thread.

    Memory consolidation works on the whole role session; model-facing
    history reads pass a context view's filter instead.
    """
    return True


def message_thread_id(message: Mapping[str, Any]) -> str:
    """The conversation thread one session message belongs to; empty if unknown.

    A message read back from storage carries ``thread_id`` itself; one still
    in memory may only have it in its metadata until it is persisted.
    """
    metadata = message.get("metadata")
    typed_metadata = metadata if isinstance(metadata, Mapping) else {}
    return str(
        message.get("thread_id") or typed_metadata.get("thread_id") or ""
    ).strip()


def effective_context_cursors(
    context_cursors: Mapping[ContextScope, int] | None, last_consolidated: int
) -> dict[ContextScope, int]:
    """各上下文的整理游标；未迁移（None）时都取 ``last_consolidated``。

    这就是旧会话的迁移规则：迁移前后每类上下文读历史的起点不变。
    """
    if context_cursors is None:
        return {scope: int(last_consolidated) for scope in CONTEXT_SCOPES}
    return {scope: int(context_cursors[scope]) for scope in CONTEXT_SCOPES}


def consolidation_cursor(session: Any, scope: ContextScope | None) -> int:
    """回合读历史、估算预算时的整理游标：此前的消息已整理，不再原文发给模型。

    ``scope`` 为 None 表示会话只有一段对话（非角色会话），用 ``last_consolidated``；
    否则取角色会话里这类上下文自己的游标，见 ``effective_context_cursors``。
    """
    last_consolidated = int(getattr(session, "last_consolidated", 0))
    if scope is None:
        return last_consolidated
    return effective_context_cursors(
        getattr(session, "context_cursors", None), last_consolidated
    )[scope]


def build_session_message(
    role: str,
    content: str,
    media: list[str] | None = None,
    **kwargs: Any,
) -> dict[str, Any]:
    """Build a private message draft without changing any session state."""
    message = {
        "role": role,
        "content": content,
        "timestamp": datetime.now().astimezone().isoformat(),
        **kwargs,
    }
    if media:
        message["media"] = list(media)
    return message


@dataclass
class Session:
    """单次对话中的 session。"""

    key: str
    messages: list[dict[str, Any]] = field(default_factory=list)
    created_at: datetime = field(default_factory=datetime.now)
    updated_at: datetime = field(default_factory=datetime.now)
    metadata: dict[str, Any] = field(default_factory=dict)
    last_consolidated: int = 0
    # 角色会话按上下文的整理游标（#523）；None 表示未迁移，各上下文取
    # last_consolidated。只由整理提交与撤销改写，见 ``set_consolidation_cursors``。
    context_cursors: dict[ContextScope, int] | None = None
    consolidation_requested: bool = False

    def add_message(
        self, role: str, content: str, media: list[str] | None = None, **kwargs: Any
    ) -> None:
        """Add a message to session."""
        self.messages.append(build_session_message(role, content, media, **kwargs))
        self.updated_at = datetime.now()

    def get_history(
        self,
        max_messages: int = 500,
        *,
        start_index: int | None = None,
        include: HistoryFilter | None = None,
    ) -> list[dict[str, Any]]:
        """将 session 消息展开为 LLM 可直接使用的 OpenAI 格式消息列表。

        ``include`` 按原始消息筛选可见历史（例如只保留某类上下文的会话）；
        窗口仍从 ``start_index`` 起算，筛掉的消息不会被更早的消息补上。
        """
        out: list[dict[str, Any]] = []
        for m in self.history_window(
            max_messages, start_index=start_index, include=include
        ):
            role = m.get("role")

            if role == "user":
                user_content = m.get("llm_user_content")
                if user_content is None:
                    text = m.get("content", "")
                    media_paths = m.get("media") or []
                    user_content = (
                        _rebuild_user_content(text, media_paths)
                        if media_paths
                        else text
                    )
                out.append(
                    {
                        "role": "user",
                        "content": with_message_source(
                            user_content,
                            MessageSource.from_metadata(
                                m.get("metadata") or {}, session_key=self.key
                            ),
                        ),
                    }
                )
                continue

            if role != "assistant":
                continue

            content = m.get("content", "") or ""
            if m.get("proactive"):
                out.extend(_build_proactive_history_messages(str(content), m))
                continue

            tool_chain: list[dict] = m.get("tool_chain") or []
            for group in tool_chain:
                calls: list[dict] = group.get("calls") or []
                if not calls:
                    continue
                assistant_msg = {
                    "role": "assistant",
                    "content": group.get("text"),
                    "tool_calls": [
                        {
                            "id": c["call_id"],
                            "type": "function",
                            "function": {
                                "name": c["name"],
                                "arguments": json.dumps(
                                    c.get("arguments", {}), ensure_ascii=False
                                ),
                            },
                        }
                        for c in calls
                    ],
                }
                reasoning_content = group.get("reasoning_content")
                if isinstance(reasoning_content, str):
                    assistant_msg["reasoning_content"] = reasoning_content
                out.append(assistant_msg)
                for c in calls:
                    out.append(
                        {
                            "role": "tool",
                            "tool_call_id": c["call_id"],
                            "content": _truncate_tool_result(c.get("result", "")),
                        }
                    )

            if content:
                content = _append_proactive_meta(content, m)
            assistant_msg = {"role": "assistant", "content": content}
            reasoning_content = m.get("reasoning_content")
            if isinstance(reasoning_content, str):
                assistant_msg["reasoning_content"] = reasoning_content
            out.append(assistant_msg)

        return out

    def get_history_tool_names(
        self,
        max_messages: int = 500,
        *,
        start_index: int | None = None,
        include: HistoryFilter | None = None,
    ) -> list[str]:
        """返回与 get_history 同一窗口内模型调用过或经 tool_search 解锁的工具名。

        按首次出现顺序去重；主动消息的工具链不进入 LLM 历史，因此也不计入。
        ``include`` 与 get_history 的同名参数一致。
        """
        names: dict[str, None] = {}
        for m in self.history_window(
            max_messages, start_index=start_index, include=include
        ):
            if m.get("role") != "assistant" or m.get("proactive"):
                continue
            for group in m.get("tool_chain") or []:
                for call in group.get("calls") or []:
                    names.setdefault(call["name"], None)
                    for name in call.get("unlocked") or []:
                        names.setdefault(name, None)
        return list(names)

    def history_window(
        self,
        max_messages: int,
        *,
        start_index: int | None = None,
        include: HistoryFilter | None = None,
    ) -> list[dict[str, Any]]:
        """截取历史窗口的原始消息，start_index 会对齐到完整 turn 的起点。

        ``include`` 在窗口内逐条筛选；没有 start_index 时先筛选再取最近
        ``max_messages`` 条，使条数上限作用在可见消息上。角色共享会话混存
        各会话的消息，读取时必须给出筛选（按上下文视图，或明确用
        ``whole_session``），漏传直接报错，不会返回未筛选的历史。
        """
        if include is None and is_role_session_key(self.key):
            raise ValueError(f"角色共享会话 {self.key} 读取历史必须指定上下文筛选")
        if start_index is not None:
            if max_messages <= 0:
                return []
            start = max(0, int(start_index))
            if start >= len(self.messages):
                return []
            # 向前回退到最近的 user 边界（保留完整 turn）
            while start > 0 and not starts_turn(self.messages[start]):
                start -= 1
            # start=0 但仍非合法边界时，向后找第一个 user 或 proactive assistant。
            messages = _align_to_user_boundary(self.messages[start:])
            if not messages:
                return []
        elif max_messages <= 0:
            return []
        else:
            visible = (
                self.messages
                if include is None
                else [m for m in self.messages if include(m)]
            )
            return visible[-max_messages:]
        return messages if include is None else [m for m in messages if include(m)]

    def clear(self) -> None:
        self.messages = []
        self.updated_at = datetime.now()
        self.last_consolidated = 0
        self.context_cursors = None
        self.consolidation_requested = False

    def set_consolidation_cursors(
        self,
        last_consolidated: int,
        context_cursors: dict[ContextScope, int] | None,
    ) -> None:
        """整理提交或撤销落盘后，把新的游标同步到缓存里的会话。

        ``context_cursors`` 为 None 表示非角色会话，只有 ``last_consolidated``。
        """
        self.last_consolidated = last_consolidated
        if context_cursors is not None:
            self.context_cursors = dict(context_cursors)
        self.updated_at = datetime.now()
