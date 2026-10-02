"""Neutral tool-hook fixtures for host loop protocol regressions.

Host tests exercise the finalize protocol (deny with ``finalize=True`` ->
truncate the remaining batch -> closing summary) with a hook that carries no
plugin policy. Repeat thresholds and exclusions belong to the
``tool_loop_guard`` plugin's own tests.
"""

from collections.abc import Sequence
from pathlib import Path
from typing import Any, cast
from unittest.mock import MagicMock

from agent.looping.core import AgentLoop
from shiori_host_testing.memory import FakeMemoryEngine
from agent.looping.ports import (
    AgentLoopConfig,
    AgentLoopDeps,
    LLMConfig,
    MemoryServices,
)
from agent.provider import LLMResponse
from agent.tool_hooks.base import ToolHook
from agent.tool_hooks.types import HookContext
from shiori_sdk.tool_hooks import HookOutcome
from shiori_sdk.tools import Tool
from agent.tools.registry import ToolRegistry


class FinalizeOnCallHook(ToolHook):
    """Denies the listed call ids with ``finalize=True`` and passes the rest.

    The hook has no notion of repetition: tests pick which call triggers the
    finalize decision, so they assert only how the host loop consumes it.
    """

    name = "test:finalize_on_call"
    event = "pre_tool_use"

    def __init__(self, *call_ids: str) -> None:
        self._call_ids = frozenset(call_ids)
        self.seen: list[str] = []

    def matches(self, ctx: HookContext) -> bool:
        return True

    async def run(self, ctx: HookContext) -> HookOutcome:
        self.seen.append(ctx.request.call_id)
        if ctx.request.call_id in self._call_ids:
            return HookOutcome(decision="deny", reason="测试要求收尾", finalize=True)
        return HookOutcome()


class DummyTool(Tool):
    """Tool with one integer argument that records each execution."""

    def __init__(self, name: str = "dummy") -> None:
        self._name = name
        self.calls: list[dict] = []

    @property
    def name(self) -> str:
        return self._name

    @property
    def description(self) -> str:
        return "dummy tool"

    @property
    def parameters(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "x": {"type": "integer"},
            },
            "required": ["x"],
        }

    async def execute(self, **kwargs) -> str:
        self.calls.append(kwargs)
        return f"ok:{kwargs.get('x')}"


class FakeProvider:
    """Replays scripted responses and records every chat request."""

    def __init__(self, responses: list[LLMResponse]) -> None:
        self._responses = list(responses)
        self.calls: list[dict] = []

    async def chat(self, **kwargs):
        self.calls.append(kwargs)
        if not self._responses:
            raise AssertionError("provider.chat called more than expected")
        return self._responses.pop(0)


def _assert_no_unresolved_tool_calls(messages: list[dict]) -> None:
    pending: set[str] = set()
    for m in messages:
        if m.get("role") == "assistant" and m.get("tool_calls"):
            for tc in m["tool_calls"]:
                call_id = tc.get("id")
                if call_id:
                    pending.add(call_id)
        elif m.get("role") == "tool":
            call_id = m.get("tool_call_id")
            if call_id in pending:
                pending.remove(call_id)
    if pending:
        raise AssertionError(
            f"unresolved tool_calls in message chain: {sorted(pending)}"
        )


class StrictProvider(FakeProvider):
    """Fails the request when any earlier assistant tool call lacks a result."""

    async def chat(self, **kwargs):
        messages = kwargs.get("messages") or []
        _assert_no_unresolved_tool_calls(messages)
        return await super().chat(**kwargs)


class ExitTool(Tool):
    """Mandatory exit tool that only counts its invocations."""

    def __init__(self, name: str = "checkpoint") -> None:
        self._name = name
        self.called = 0

    @property
    def name(self) -> str:
        return self._name

    @property
    def description(self) -> str:
        return "exit tool"

    @property
    def parameters(self) -> dict:
        return {
            "type": "object",
            "properties": {"note": {"type": "string"}},
            "required": [],
        }

    async def execute(self, **kwargs) -> str:
        self.called += 1
        return "noted"


def make_agent_loop_with_tools(
    tmp_path: Path,
    provider: FakeProvider,
    tools_to_register: list[Tool],
    *,
    hooks: Sequence[ToolHook] = (),
    tool_search_enabled: bool = False,
) -> AgentLoop:
    """Builds a real ``AgentLoop`` with the given tools and tool hooks."""
    tools = ToolRegistry()
    for tool in tools_to_register:
        tools.register(tool)
    loop = AgentLoop(
        AgentLoopDeps(
            bus=MagicMock(),
            provider=cast(Any, provider),
            tools=tools,
            session_manager=MagicMock(),
            workspace=tmp_path,
            memory_services=MemoryServices(engine=FakeMemoryEngine(tmp_path)),
        ),
        AgentLoopConfig(
            llm=LLMConfig(
                max_iterations=10,
                tool_search_enabled=tool_search_enabled,
            )
        ),
    )
    loop.add_tool_hooks(list(hooks))
    return loop
