"""Committed turn observation shared with memory engines."""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from shiori_sdk.tool_chain import ToolCallGroup


@dataclass(frozen=True)
class TurnCommitted:
    """Committed turn snapshot observed by the semantic memory engine."""

    session_key: str
    channel: str
    chat_id: str
    input_message: str
    persisted_user_message: str | None
    assistant_response: str
    tools_used: list[str]
    thinking: str | None = None
    raw_reply: str | None = None
    meme_tag: str | None = None
    meme_media_count: int | None = None
    tool_chain_raw: list[dict[str, Any]] = field(default_factory=list)
    tool_call_groups: list["ToolCallGroup"] = field(default_factory=list)
    timestamp: datetime | None = None
    post_reply_budget: dict[str, int] = field(default_factory=dict)
    react_stats: dict[str, int] = field(default_factory=dict)
    extra: dict[str, Any] = field(default_factory=dict)
    role_id: str = ""
    request_id: str = ""
    thread_id: str = ""
    total_tokens: int | None = None
    thinking_duration_ms: int | None = None
