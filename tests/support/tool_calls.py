"""Neutral tool-call fixtures for host loop protocol regressions.

Host tests exercise the finalize protocol (``ToolVeto(finalize=True)`` ->
truncate the remaining batch -> closing summary) with a ``ToolCalling``
handler that carries no plugin policy. Repeat thresholds and exclusions belong
to the ``tool_loop_guard`` plugin's own tests.
"""

from tests.support.generation_getters import bound_affection, bound_reply_policy

from collections.abc import Awaitable, Callable
from pathlib import Path
from typing import Any, cast
from unittest.mock import MagicMock

from agent.core.turn_events import core_kernel
from agent.looping.core import AgentLoop
from shiori_host_testing.memory import FakeMemoryEngine
from agent.looping.ports import (
    AgentLoopConfig,
    AgentLoopDeps,
    LLMConfig,
    MemoryServices,
)
from agent.provider import LLMResponse
from shiori_sdk.core.tools import ToolCalled, ToolCalling, ToolVeto
from shiori_sdk.kernel import Context, Kernel, PluginSpec, Scope, Veto
from shiori_sdk.tools import Tool
from agent.tools.registry import ToolRegistry

type ToolCallingHandler = Callable[[ToolCalling], Awaitable[ToolCalling | Veto]]
type ToolCalledHandler = Callable[[ToolCalled], Awaitable[ToolCalled]]


def kernel_with(
    *calling: ToolCallingHandler,
    called: tuple[ToolCalledHandler, ...] = (),
    on: tuple[tuple[type[Any], Callable[[Any], Awaitable[Any]]], ...] = (),
) -> Kernel:
    """A core kernel (core checks installed) running the given event handlers.

    Each handler joins under its own stand-in plugin, in the given order:
    ``calling`` on ``ToolCalling``, ``called`` on ``ToolCalled``, then each
    ``(event type, handler)`` pair of ``on``.
    """
    kernel = core_kernel()

    async def no_setup(_: Context) -> None:
        return None

    subscriptions: list[tuple[type[Any], Callable[[Any], Awaitable[Any]]]] = [
        (ToolCalling, handler) for handler in calling
    ]
    subscriptions += [(ToolCalled, handler) for handler in called]
    subscriptions += on
    for index, (event_type, handler) in enumerate(subscriptions):
        plugin_id = f"test_{index}"
        context = Context(kernel, PluginSpec(plugin_id, no_setup), Scope(plugin_id))
        context.on(event_type, handler)  # type: ignore[arg-type]
    return kernel


class FinalizeOnCall:
    """Vetoes the listed call ids with ``finalize=True`` and passes the rest.

    The handler has no notion of repetition: tests pick which call triggers the
    finalize decision, so they assert only how the host loop consumes it.
    """

    def __init__(self, *call_ids: str) -> None:
        self._call_ids = frozenset(call_ids)
        self.seen: list[str] = []

    async def __call__(self, event: ToolCalling) -> ToolCalling | Veto:
        self.seen.append(event.call_id)
        if event.call_id in self._call_ids:
            return ToolVeto("测试要求收尾", finalize=True)
        return event


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
    handlers: tuple[ToolCallingHandler, ...] = (),
    tool_search_enabled: bool = False,
) -> AgentLoop:
    """Builds a real ``AgentLoop`` with the given tools and ``ToolCalling`` handlers."""
    tools = ToolRegistry()
    for tool in tools_to_register:
        tools.register(tool)
    memory_engine = FakeMemoryEngine(tmp_path)
    loop = AgentLoop(
        AgentLoopDeps(
            reply_policy=bound_reply_policy(),
            affection=bound_affection(),
            bus=MagicMock(),
            provider=cast(Any, provider),
            tools=tools,
            session_manager=MagicMock(),
            workspace=tmp_path,
            memory_services=MemoryServices(current_engine=lambda: memory_engine),
        ),
        AgentLoopConfig(
            llm=LLMConfig(
                max_iterations=10,
                tool_search_enabled=tool_search_enabled,
            )
        ),
    )
    kernel = kernel_with(*handlers)
    loop.bind_kernel(lambda: kernel)
    return loop
