"""Session 数据模型。"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from .helpers import (
    _align_to_user_boundary,
    _append_proactive_meta,
    _build_proactive_history_messages,
    _rebuild_user_content,
    _truncate_tool_result,
)


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
        msg = {
            "role": role,
            "content": content,
            "timestamp": datetime.now().astimezone().isoformat(),
            **kwargs,
        }
        if media:
            msg["media"] = list(media)
        self.messages.append(msg)
        self.updated_at = datetime.now()

    def get_history(
        self,
        max_messages: int = 500,
        *,
        start_index: int | None = None,
    ) -> list[dict[str, Any]]:
        """将 session 消息展开为 LLM 可直接使用的 OpenAI 格式消息列表。"""
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
            messages = []
        else:
            messages = self.messages[-max_messages:]
        out: list[dict[str, Any]] = []
        for m in messages:
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
                out.append({"role": "user", "content": user_content})
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

    def clear(self) -> None:
        self.messages = []
        self.updated_at = datetime.now()
        self.last_consolidated = 0
        self.consolidation_requested = False
