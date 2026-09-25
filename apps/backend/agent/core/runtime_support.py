from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime
from typing import Protocol

from agent.lifecycle.types import PromptRenderInput, PromptRenderResult
from core.roles.reply_state import RoleReply


@dataclass
class MemoryConfig:
    window: int = 40


@dataclass
class LLMServices:
    provider: object
    light_provider: object


@dataclass
class MemoryServices:
    engine: object


@dataclass
class ToolDiscoveryState:
    """解析 tool_search 结果中的解锁名单。

    跨轮可见性不在这里维护：会话历史的 tool_chain 记录了调用与解锁过的工具，
    每轮由 Session.get_history_tool_names 推导。
    """

    def unlock_names_from_result(self, result_json: str) -> list[str]:
        try:
            data = json.loads(result_json)
            raw_unlocked = data.get("unlocked")
            raw_names: list[object]
            if isinstance(raw_unlocked, list):
                raw_names = raw_unlocked
            else:
                raw_names = [
                    item.get("name")
                    for item in data.get("matched", [])
                    if isinstance(item, dict)
                ]
            names: list[str] = []
            seen: set[str] = set()
            for item in raw_names:
                if isinstance(item, str) and item and item not in seen:
                    names.append(item)
                    seen.add(item)
            return names
        except Exception:
            return []

    def unlock_from_result(self, result_json: str) -> set[str]:
        """Parse a tool_search JSON result and return the tool names in 'matched'.

        Replaces the previous module-level _unlock_from_tool_search() helper.
        Pure parsing — no mutation of external
        state; caller decides what to do with the returned names.
        """
        return set(self.unlock_names_from_result(result_json))


class SessionLike(Protocol):
    key: str
    messages: list[dict]
    metadata: dict[str, object]
    last_consolidated: int

    def get_history(
        self,
        max_messages: int = 500,
        *,
        start_index: int | None = None,
    ) -> list[dict]: ...
    def get_history_tool_names(
        self,
        max_messages: int = 500,
        *,
        start_index: int | None = None,
    ) -> list[str]: ...
    def add_message(self, role: str, content: str, media=None, **kwargs) -> None: ...


@dataclass
class TurnRunResult:
    reply: str | None
    tools_used: list[str] = field(default_factory=list)
    tool_chain: list[dict] = field(default_factory=list)
    thinking: str | None = None
    streamed: bool = False
    context_retry: dict[str, object] = field(default_factory=dict)
    # Kept outside `context_retry`: that dict gets snapshotted verbatim into
    # persisted message/outbound metadata (JSON), so it must stay JSON-safe.
    role_reply: RoleReply | None = None
    role_reply_mood_fresh: bool = False


class AgentLoopRunner(Protocol):
    async def __call__(
        self,
        initial_messages: list[dict],
        request_time: datetime | None = None,
        preloaded_tools: set[str] | None = None,
        tool_event_session_key: str = "",
        tool_event_channel: str = "",
        tool_event_chat_id: str = "",
        tool_execution_context: dict[str, str] | None = None,
    ) -> tuple[str, list[str], list[dict], set[str] | None, str | None]: ...


class PromptRenderRunner(Protocol):
    async def __call__(
        self,
        input: PromptRenderInput,
    ) -> PromptRenderResult: ...
