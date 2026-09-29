"""Session 数据模型。"""

from __future__ import annotations

import json
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from core.common.message_source import MessageSource, with_message_source

from .helpers import (
    _align_to_user_boundary,
    _append_proactive_meta,
    _build_proactive_history_messages,
    _rebuild_user_content,
    _truncate_tool_result,
)

INTERRUPTED_TURN_METADATA_KEY = "interrupted_turn"

# Decides whether one raw session message is visible to a history read.
HistoryFilter = Callable[[dict[str, Any]], bool]


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
        for m in self._history_window(max_messages, start_index, include):
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
        for m in self._history_window(max_messages, start_index, include):
            if m.get("role") != "assistant" or m.get("proactive"):
                continue
            for group in m.get("tool_chain") or []:
                for call in group.get("calls") or []:
                    names.setdefault(call["name"], None)
                    for name in call.get("unlocked") or []:
                        names.setdefault(name, None)
        return list(names)

    def _history_window(
        self,
        max_messages: int,
        start_index: int | None,
        include: HistoryFilter | None = None,
    ) -> list[dict[str, Any]]:
        """截取历史窗口的原始消息，start_index 会对齐到完整 turn 的起点。

        ``include`` 在窗口内逐条筛选；没有 start_index 时先筛选再取最近
        ``max_messages`` 条，使条数上限作用在可见消息上。
        """
        if start_index is not None:
            if max_messages <= 0:
                return []
            start = max(0, int(start_index))
            if start >= len(self.messages):
                return []
            # 向前回退到最近的 user 边界（保留完整 turn）
            while (
                start > 0
                and self.messages[start].get("role") != "user"
                and not (
                    self.messages[start].get("role") == "assistant"
                    and self.messages[start].get("proactive")
                )
            ):
                start -= 1
            # start=0 但仍非合法边界时，向后找第一个 user 或 proactive assistant。
            messages = self.messages[start:]
            if messages and not (
                messages[0].get("role") == "user"
                or (
                    messages[0].get("role") == "assistant"
                    and messages[0].get("proactive")
                )
            ):
                messages = _align_to_user_boundary(messages)
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
        self.consolidation_requested = False
