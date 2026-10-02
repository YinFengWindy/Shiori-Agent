"""Real host loop assembly for public plugin-hook integration regressions."""

import asyncio
import tempfile
from pathlib import Path
from typing import Any, cast
from unittest.mock import MagicMock

import httpx
import pytest
from shiori_sdk.testing.packages import plugin_directory, stage_plugin_package

from agent.looping.core import AgentLoop
from shiori_host_testing.memory import FakeMemoryEngine
from agent.looping.ports import (
    AgentLoopConfig,
    AgentLoopDeps,
    LLMConfig,
    MemoryServices,
)
from agent.plugin_host import HostServices, PluginKernel
from agent.provider import LLMResponse
from agent.subagent import SubAgent
from agent.tool_hooks.base import ToolHook
from shiori_sdk.tools import Tool
from agent.tools.registry import ToolRegistry
from bus.event_bus import EventBus
from core.net.http import (
    SharedHttpResources,
    clear_default_shared_http_resources,
    configure_default_shared_http_resources,
)

PLUGIN_DIR = plugin_directory("tool_loop_guard")


class _DummyTool(Tool):
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


class _FakeProvider:
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


class _StrictProvider(_FakeProvider):
    async def chat(self, **kwargs):
        messages = kwargs.get("messages") or []
        _assert_no_unresolved_tool_calls(messages)
        return await super().chat(**kwargs)


@pytest.fixture(autouse=True)
def _shared_http_resources(monkeypatch):
    def reject_network(request: httpx.Request) -> httpx.Response:
        raise AssertionError(f"unexpected HTTP request: {request.method} {request.url}")

    client_type = httpx.AsyncClient

    def offline_client(**kwargs):
        return client_type(transport=httpx.MockTransport(reject_network), **kwargs)

    # Keep real requesters/resources while avoiding TLS setup for offline loop tests.
    with monkeypatch.context() as patch:
        patch.setattr(httpx, "AsyncClient", offline_client)
        resources = SharedHttpResources()
    configure_default_shared_http_resources(resources)
    try:
        yield
    finally:
        clear_default_shared_http_resources(resources)
        asyncio.run(resources.aclose())


class _ExitTool(Tool):
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


def _make_agent_loop_with_tools(
    tmp_path: Path,
    provider: _FakeProvider,
    tools_to_register: list[Tool],
    *,
    tool_search_enabled: bool = False,
) -> AgentLoop:
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
    loop.add_tool_hooks(_tool_loop_guard_hooks())
    return loop


def _make_agent_loop(tmp_path: Path, provider: _FakeProvider, tool: Tool) -> AgentLoop:
    return _make_agent_loop_with_tools(tmp_path, provider, [tool])


def _tool_loop_guard_hooks(
    *, plugin_configs: dict[str, dict[str, Any]] | None = None
) -> list[ToolHook]:
    with tempfile.TemporaryDirectory() as tmp:
        plugin_dir = Path(tmp) / "tool_loop_guard"
        stage_plugin_package(PLUGIN_DIR, plugin_dir)
        kernel = PluginKernel(
            [Path(tmp)],
            services=HostServices(
                event_bus=EventBus(), plugin_configs=plugin_configs or {}
            ),
        )
        asyncio.run(kernel.load_all())
        return kernel.tool_hooks


def _install_tool_loop_guard(subagent: SubAgent) -> SubAgent:
    subagent.add_tool_hooks(_tool_loop_guard_hooks())
    return subagent
