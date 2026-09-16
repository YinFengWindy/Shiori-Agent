import asyncio
import tempfile
from pathlib import Path
from typing import Any, cast
from unittest.mock import MagicMock

import httpx
import pytest
from shiori_plugin_testkit.packages import stage_plugin_package

from agent.looping.core import AgentLoop
from agent.looping.ports import (
    AgentLoopConfig,
    AgentLoopDeps,
    LLMConfig,
    MemoryServices,
)
from agent.plugin_host import HostServices, PluginKernel
from agent.provider import LLMResponse, ToolCall
from agent.subagent import SubAgent
from agent.tool_hooks.base import ToolHook
from agent.tools.base import Tool
from agent.tools.registry import ToolRegistry
from bus.event_bus import EventBus
from core.net.http import (
    SharedHttpResources,
    clear_default_shared_http_resources,
    configure_default_shared_http_resources,
)
from shiori_plugin_testkit.memory import FakeMemoryEngine

PLUGIN_DIR = Path(__file__).resolve().parents[1]


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
        patch.setattr("core.net.http.httpx.AsyncClient", offline_client)
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


def _make_bare_agent_loop(
    tmp_path: Path, provider: _FakeProvider, tool: Tool
) -> AgentLoop:
    """构造不带默认 tool_loop_guard hook 的 AgentLoop，供测试自行装配指定配置的 hook。

    ``_make_agent_loop``/``_make_agent_loop_with_tools`` 会用无配置（默认 repeat_limit=3）
    的 hook 预先装好 loop，若测试还想验证自定义 repeat_limit，需要绕开这份默认装配，
    否则两个 hook 会同时生效，配置更宽松的一份也会被更严格的默认值抢先拦截。
    """
    tools = ToolRegistry()
    tools.register(tool)
    return AgentLoop(
        AgentLoopDeps(
            bus=MagicMock(),
            provider=cast(Any, provider),
            tools=tools,
            session_manager=MagicMock(),
            workspace=tmp_path,
            memory_services=MemoryServices(engine=FakeMemoryEngine(tmp_path)),
        ),
        AgentLoopConfig(llm=LLMConfig(max_iterations=10)),
    )


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


def test_tool_loop_guard_hook_name_matches_legacy_convention():
    """hook 名由 ToolHooksCapability 统一生成，须与旧系统
    f"plugin:{instance.name}:{md.handler_name}" 逐字一致（#182 评审）。"""
    hooks = _tool_loop_guard_hooks()

    assert [h.name for h in hooks] == [
        "plugin:tool_loop_guard:detect_repeated_tool_call"
    ]


def test_repeat_limit_config_actually_takes_effect_after_v2_migration(tmp_path):
    """[plugins.tool_loop_guard].repeat_limit 迁移前从未生效（#182 评审独立核实）：

    旧 Plugin ABC 版本既无 ConfigModel 也无 _conf_schema.json，_load_plugin_config
    因此恒返回 None，self.context.config 恒为 None，repeat_limit 硬编码为 3；
    用户在 config.toml 里配置的值被静默吞掉。迁移到 v2 后 ctx.config 读取真实的
    services.plugin_configs，配置现在真的生效——这是修了一个 bug，不是刻意变更，
    这里用 repeat_limit=5 时连续 4 次相同调用都不应被拦截来证明。
    """
    tool = _DummyTool("dummy")
    provider = _FakeProvider(
        [
            LLMResponse(content="", tool_calls=[ToolCall("c1", "dummy", {"x": 1})]),
            LLMResponse(content="", tool_calls=[ToolCall("c2", "dummy", {"x": 1})]),
            LLMResponse(content="", tool_calls=[ToolCall("c3", "dummy", {"x": 1})]),
            LLMResponse(content="", tool_calls=[ToolCall("c4", "dummy", {"x": 1})]),
            LLMResponse(
                content="已完成阶段A，剩余阶段B，下一步继续补齐", tool_calls=[]
            ),
        ]
    )
    loop = _make_bare_agent_loop(tmp_path, provider, tool)
    loop.add_tool_hooks(
        _tool_loop_guard_hooks(plugin_configs={"tool_loop_guard": {"repeat_limit": 5}})
    )

    final, tools_used, _, _vn, _ = asyncio.run(
        loop._run_agent_loop([{"role": "user", "content": "test"}])
    )

    # repeat_limit=5 时，4 次相同签名调用都低于阈值，全部放行；
    # 若配置像迁移前那样被吞掉（硬编码为 3），第 3 次就会被拦截，只会执行 2 次
    assert len(tool.calls) == 4
    assert tools_used == ["dummy", "dummy", "dummy", "dummy"]


def test_repeat_limit_defaults_to_three_when_not_configured(tmp_path):
    """未配置 [plugins.tool_loop_guard] 时，repeat_limit 缺省仍是硬编码的 3。"""
    tool = _DummyTool("dummy")
    provider = _FakeProvider(
        [
            LLMResponse(content="", tool_calls=[ToolCall("c1", "dummy", {"x": 1})]),
            LLMResponse(content="", tool_calls=[ToolCall("c2", "dummy", {"x": 1})]),
            LLMResponse(content="", tool_calls=[ToolCall("c3", "dummy", {"x": 1})]),
            LLMResponse(
                content="已完成阶段A，剩余阶段B，下一步继续补齐", tool_calls=[]
            ),
        ]
    )
    loop = _make_bare_agent_loop(tmp_path, provider, tool)
    loop.add_tool_hooks(_tool_loop_guard_hooks(plugin_configs={}))

    final, tools_used, _, _vn, _ = asyncio.run(
        loop._run_agent_loop([{"role": "user", "content": "test"}])
    )

    assert len(tool.calls) == 2
    assert tools_used == ["dummy", "dummy"]


def test_agent_loop_breaks_on_repeated_same_signature_and_returns_summary(tmp_path):
    tool = _DummyTool("dummy")
    provider = _FakeProvider(
        [
            LLMResponse(content="", tool_calls=[ToolCall("c1", "dummy", {"x": 1})]),
            LLMResponse(content="", tool_calls=[ToolCall("c2", "dummy", {"x": 1})]),
            LLMResponse(content="", tool_calls=[ToolCall("c3", "dummy", {"x": 1})]),
            LLMResponse(
                content="已完成阶段A，剩余阶段B，下一步继续补齐", tool_calls=[]
            ),
        ]
    )
    loop = _make_agent_loop(tmp_path, provider, tool)

    final, tools_used, _, _vn, _ = asyncio.run(
        loop._run_agent_loop([{"role": "user", "content": "test"}])
    )

    assert "最大迭代" not in final
    assert "下一步" in final
    # 第三次重复签名会被提前拦截，不应执行第三次工具
    assert len(tool.calls) == 2
    assert tools_used == ["dummy", "dummy"]


def test_agent_loop_breaks_on_repeated_multi_tool_batch_and_keeps_chain_closed(
    tmp_path,
):
    tool_a = _DummyTool("a")
    tool_b = _DummyTool("b")
    provider = _StrictProvider(
        [
            LLMResponse(
                content="",
                tool_calls=[
                    ToolCall("a1", "a", {"x": 1}),
                    ToolCall("b1", "b", {"x": 2}),
                ],
            ),
            LLMResponse(
                content="",
                tool_calls=[
                    ToolCall("a2", "a", {"x": 1}),
                    ToolCall("b2", "b", {"x": 2}),
                ],
            ),
            LLMResponse(
                content="",
                tool_calls=[
                    ToolCall("a3", "a", {"x": 1}),
                    ToolCall("b3", "b", {"x": 2}),
                ],
            ),
            LLMResponse(content="已总结当前进度", tool_calls=[]),
        ]
    )
    loop = _make_agent_loop_with_tools(tmp_path, provider, [tool_a, tool_b])

    final, tools_used, _, _vn, _ = asyncio.run(
        loop._run_agent_loop([{"role": "user", "content": "test"}])
    )

    assert "已总结" in final
    assert tools_used == ["a", "b", "a", "b"]
    assert len(tool_a.calls) == 2
    assert len(tool_b.calls) == 2


def test_agent_loop_breaks_on_repeated_unlocked_tool_request(tmp_path):
    tool = _DummyTool("hidden_tool")
    provider = _StrictProvider(
        [
            LLMResponse(
                content="", tool_calls=[ToolCall("h1", "hidden_tool", {"x": 1})]
            ),
            LLMResponse(
                content="", tool_calls=[ToolCall("h2", "hidden_tool", {"x": 1})]
            ),
            LLMResponse(
                content="", tool_calls=[ToolCall("h3", "hidden_tool", {"x": 1})]
            ),
            LLMResponse(content="已总结当前进度", tool_calls=[]),
        ]
    )
    loop = _make_agent_loop_with_tools(
        tmp_path,
        provider,
        [tool],
        tool_search_enabled=True,
    )

    final, tools_used, _, _vn, _ = asyncio.run(
        loop._run_agent_loop([{"role": "user", "content": "test"}])
    )

    assert "已总结" in final
    assert tools_used == []
    assert len(tool.calls) == 0


def test_agent_loop_does_not_false_positive_when_args_change(tmp_path):
    tool = _DummyTool("dummy")
    provider = _FakeProvider(
        [
            LLMResponse(content="", tool_calls=[ToolCall("c1", "dummy", {"x": 1})]),
            LLMResponse(content="", tool_calls=[ToolCall("c2", "dummy", {"x": 2})]),
            LLMResponse(content="done", tool_calls=[]),
        ]
    )
    loop = _make_agent_loop(tmp_path, provider, tool)

    final, _, _, _vn, _ = asyncio.run(
        loop._run_agent_loop([{"role": "user", "content": "test"}])
    )

    assert final == "done"
    assert len(tool.calls) == 2


def test_agent_loop_max_iterations_returns_progress_summary_not_template(tmp_path):
    tool = _DummyTool("dummy")
    provider = _FakeProvider(
        [
            LLMResponse(content="", tool_calls=[ToolCall("c1", "dummy", {"x": 1})]),
            LLMResponse(
                content="目前完成数据抓取，待整理结论，下一步继续", tool_calls=[]
            ),
        ]
    )
    loop = _make_agent_loop(tmp_path, provider, tool)
    loop.max_iterations = 1

    final, _, _, _vn, _ = asyncio.run(
        loop._run_agent_loop([{"role": "user", "content": "test"}])
    )

    assert "最大迭代" not in final
    assert "下一步" in final


def test_subagent_marks_tool_loop_and_summarizes():
    tool = _DummyTool("dummy")
    provider = _FakeProvider(
        [
            LLMResponse(content="", tool_calls=[ToolCall("s1", "dummy", {"x": 1})]),
            LLMResponse(content="", tool_calls=[ToolCall("s2", "dummy", {"x": 1})]),
            LLMResponse(content="", tool_calls=[ToolCall("s3", "dummy", {"x": 1})]),
            LLMResponse(content="已完成部分，剩余部分下次继续", tool_calls=[]),
        ]
    )
    subagent = SubAgent(
        provider=cast(Any, provider), model="m", tools=[tool], max_iterations=10
    )
    _install_tool_loop_guard(subagent)

    result = asyncio.run(subagent.run("do work"))

    assert subagent.last_exit_reason == "tool_loop"
    assert "最大迭代" not in result
    assert len(tool.calls) == 2


def test_subagent_breaks_on_repeated_multi_tool_batch_with_closed_chain():
    tool_a = _DummyTool("a")
    tool_b = _DummyTool("b")
    provider = _StrictProvider(
        [
            LLMResponse(
                content="",
                tool_calls=[
                    ToolCall("a1", "a", {"x": 1}),
                    ToolCall("b1", "b", {"x": 2}),
                ],
            ),
            LLMResponse(
                content="",
                tool_calls=[
                    ToolCall("a2", "a", {"x": 1}),
                    ToolCall("b2", "b", {"x": 2}),
                ],
            ),
            LLMResponse(
                content="",
                tool_calls=[
                    ToolCall("a3", "a", {"x": 1}),
                    ToolCall("b3", "b", {"x": 2}),
                ],
            ),
            LLMResponse(content="已总结当前进度", tool_calls=[]),
        ]
    )
    subagent = SubAgent(
        provider=cast(Any, provider),
        model="m",
        tools=[tool_a, tool_b],
        max_iterations=10,
    )
    _install_tool_loop_guard(subagent)

    result = asyncio.run(subagent.run("do work"))

    assert subagent.last_exit_reason == "tool_loop"
    assert "已总结" in result
    assert len(tool_a.calls) == 2
    assert len(tool_b.calls) == 2


def test_subagent_no_false_positive_when_same_tool_but_different_args():
    tool = _DummyTool("dummy")
    provider = _FakeProvider(
        [
            LLMResponse(content="", tool_calls=[ToolCall("s1", "dummy", {"x": 1})]),
            LLMResponse(content="", tool_calls=[ToolCall("s2", "dummy", {"x": 2})]),
            LLMResponse(content="all done", tool_calls=[]),
        ]
    )
    subagent = SubAgent(
        provider=cast(Any, provider), model="m", tools=[tool], max_iterations=10
    )
    _install_tool_loop_guard(subagent)

    result = asyncio.run(subagent.run("do work"))

    assert subagent.last_exit_reason == "completed"
    assert result == "all done"
    assert len(tool.calls) == 2


def test_subagent_ignores_repeated_task_output_in_loop_guard():
    tool = _DummyTool("task_output")
    provider = _FakeProvider(
        [
            LLMResponse(
                content="", tool_calls=[ToolCall("s1", "task_output", {"x": 1})]
            ),
            LLMResponse(
                content="", tool_calls=[ToolCall("s2", "task_output", {"x": 1})]
            ),
            LLMResponse(
                content="", tool_calls=[ToolCall("s3", "task_output", {"x": 1})]
            ),
            LLMResponse(content="状态已确认", tool_calls=[]),
        ]
    )
    subagent = SubAgent(
        provider=cast(Any, provider), model="m", tools=[tool], max_iterations=10
    )
    _install_tool_loop_guard(subagent)

    result = asyncio.run(subagent.run("看后台任务状态"))

    assert subagent.last_exit_reason == "completed"
    assert result == "状态已确认"
    assert len(tool.calls) == 3


def test_subagent_ignores_repeated_task_stop_in_loop_guard():
    tool = _DummyTool("task_stop")
    provider = _FakeProvider(
        [
            LLMResponse(content="", tool_calls=[ToolCall("s1", "task_stop", {"x": 1})]),
            LLMResponse(content="", tool_calls=[ToolCall("s2", "task_stop", {"x": 1})]),
            LLMResponse(content="", tool_calls=[ToolCall("s3", "task_stop", {"x": 1})]),
            LLMResponse(content="任务已停止", tool_calls=[]),
        ]
    )
    subagent = SubAgent(
        provider=cast(Any, provider), model="m", tools=[tool], max_iterations=10
    )
    _install_tool_loop_guard(subagent)

    result = asyncio.run(subagent.run("停止后台任务"))

    assert subagent.last_exit_reason == "completed"
    assert result == "任务已停止"
    assert len(tool.calls) == 3


def test_subagent_keeps_tool_result_clean():
    tool = _DummyTool("shell")
    provider = _FakeProvider(
        [
            LLMResponse(
                content="",
                tool_calls=[
                    ToolCall("s1", "shell", {"x": 1, "command": "pacman -S jq"})
                ],
            ),
            LLMResponse(content="done", tool_calls=[]),
        ]
    )
    subagent = SubAgent(
        provider=cast(Any, provider),
        model="m",
        tools=[tool],
        max_iterations=10,
    )

    result = asyncio.run(subagent.run("do work"))

    assert result == "done"
    tool_messages = [
        m for m in provider.calls[1]["messages"] if m.get("role") == "tool"
    ]
    assert len(tool_messages) == 1
    assert tool_messages[0]["content"] == "ok:1"


def test_subagent_keeps_repeated_tool_results_clean():
    tool = _DummyTool("shell")
    provider = _FakeProvider(
        [
            LLMResponse(
                content="",
                tool_calls=[
                    ToolCall("s1", "shell", {"x": 1, "command": "pacman -S jq"})
                ],
            ),
            LLMResponse(
                content="",
                tool_calls=[
                    ToolCall("s2", "shell", {"x": 2, "command": "pacman -S git"})
                ],
            ),
            LLMResponse(content="done", tool_calls=[]),
        ]
    )
    subagent = SubAgent(
        provider=cast(Any, provider),
        model="m",
        tools=[tool],
        max_iterations=10,
    )

    result = asyncio.run(subagent.run("do work"))

    assert result == "done"
    second_round_tool_messages = [
        m for m in provider.calls[2]["messages"] if m.get("role") == "tool"
    ]
    assert len(second_round_tool_messages) == 2
    assert second_round_tool_messages[0]["content"] == "ok:1"
    assert second_round_tool_messages[1]["content"] == "ok:2"


def test_subagent_unknown_tool_not_recorded_in_tools_called():
    provider = _FakeProvider(
        [
            LLMResponse(
                content="", tool_calls=[ToolCall("s1", "ghost_tool", {"x": 1})]
            ),
            LLMResponse(content="done", tool_calls=[]),
        ]
    )
    subagent = SubAgent(
        provider=cast(Any, provider),
        model="m",
        tools=[],
        max_iterations=10,
    )

    result = asyncio.run(subagent.run("do work"))

    assert result == "done"
    assert subagent.tools_called == []


def test_agent_loop_does_not_trigger_on_two_repeats_only(tmp_path):
    tool = _DummyTool("dummy")
    provider = _FakeProvider(
        [
            LLMResponse(content="", tool_calls=[ToolCall("c1", "dummy", {"x": 1})]),
            LLMResponse(content="", tool_calls=[ToolCall("c2", "dummy", {"x": 1})]),
            LLMResponse(content="final", tool_calls=[]),
        ]
    )
    loop = _make_agent_loop(tmp_path, provider, tool)

    final, _, _, _vn, _ = asyncio.run(
        loop._run_agent_loop([{"role": "user", "content": "t"}])
    )

    assert final == "final"
    assert len(tool.calls) == 2


def test_agent_loop_ignores_repeated_task_output_in_loop_guard(tmp_path):
    tool = _DummyTool("task_output")
    provider = _FakeProvider(
        [
            LLMResponse(
                content="", tool_calls=[ToolCall("c1", "task_output", {"x": 1})]
            ),
            LLMResponse(
                content="", tool_calls=[ToolCall("c2", "task_output", {"x": 1})]
            ),
            LLMResponse(
                content="", tool_calls=[ToolCall("c3", "task_output", {"x": 1})]
            ),
            LLMResponse(content="状态已确认", tool_calls=[]),
        ]
    )
    loop = _make_agent_loop(tmp_path, provider, tool)

    final, _, _, _vn, _ = asyncio.run(
        loop._run_agent_loop([{"role": "user", "content": "看后台任务状态"}])
    )

    assert final == "状态已确认"
    assert len(tool.calls) == 3


def test_agent_loop_ignores_repeated_task_stop_in_loop_guard(tmp_path):
    tool = _DummyTool("task_stop")
    provider = _FakeProvider(
        [
            LLMResponse(content="", tool_calls=[ToolCall("c1", "task_stop", {"x": 1})]),
            LLMResponse(content="", tool_calls=[ToolCall("c2", "task_stop", {"x": 1})]),
            LLMResponse(content="", tool_calls=[ToolCall("c3", "task_stop", {"x": 1})]),
            LLMResponse(content="任务已停止", tool_calls=[]),
        ]
    )
    loop = _make_agent_loop(tmp_path, provider, tool)

    final, _, _, _vn, _ = asyncio.run(
        loop._run_agent_loop([{"role": "user", "content": "停止后台任务"}])
    )

    assert final == "任务已停止"
    assert len(tool.calls) == 3


def test_agent_loop_does_not_false_positive_when_tool_order_changes(tmp_path):
    t1 = _DummyTool("a")
    t2 = _DummyTool("b")
    provider = _FakeProvider(
        [
            LLMResponse(
                content="",
                tool_calls=[
                    ToolCall("r1-1", "a", {"x": 1}),
                    ToolCall("r1-2", "b", {"x": 1}),
                ],
            ),
            LLMResponse(
                content="",
                tool_calls=[
                    ToolCall("r2-1", "b", {"x": 1}),
                    ToolCall("r2-2", "a", {"x": 1}),
                ],
            ),
            LLMResponse(content="ok", tool_calls=[]),
        ]
    )

    tools = ToolRegistry()
    tools.register(t1)
    tools.register(t2)
    loop = AgentLoop(
        AgentLoopDeps(
            bus=MagicMock(),
            provider=cast(Any, provider),
            tools=tools,
            session_manager=MagicMock(),
            workspace=tmp_path,
            memory_services=MemoryServices(engine=FakeMemoryEngine(tmp_path)),
        ),
        AgentLoopConfig(llm=LLMConfig(max_iterations=10)),
    )

    final, _, _, _vn, _ = asyncio.run(
        loop._run_agent_loop([{"role": "user", "content": "t"}])
    )

    assert final == "ok"
    assert len(t1.calls) == 2
    assert len(t2.calls) == 2


def test_subagent_max_iterations_returns_summary_and_reason():
    tool = _DummyTool("dummy")
    provider = _FakeProvider(
        [
            LLMResponse(content="", tool_calls=[ToolCall("s1", "dummy", {"x": 1})]),
            LLMResponse(content="已完成检索，剩余整理，下一步继续", tool_calls=[]),
        ]
    )
    subagent = SubAgent(
        provider=cast(Any, provider),
        model="m",
        tools=[tool],
        max_iterations=1,
    )

    result = asyncio.run(subagent.run("do work"))

    assert subagent.last_exit_reason == "forced_summary"
    assert "最大迭代" not in result
    assert "下一步" in result
    assert provider.calls[-1]["tools"] == []


def test_subagent_max_iterations_summary_failure_uses_fallback():
    tool = _DummyTool("dummy")

    class _SummaryFailProvider(_FakeProvider):
        async def chat(self, **kwargs):
            self.calls.append(kwargs)
            if len(self.calls) == 1:
                return LLMResponse(
                    content="",
                    tool_calls=[ToolCall("s1", "dummy", {"x": 1})],
                )
            raise RuntimeError("summary failed")

    provider = _SummaryFailProvider([])
    subagent = SubAgent(
        provider=cast(Any, provider),
        model="m",
        tools=[tool],
        max_iterations=1,
    )

    result = asyncio.run(subagent.run("do work"))

    assert subagent.last_exit_reason == "forced_summary_fallback"
    assert "当前进度" in result or "关键步骤" in result


def test_agent_loop_summary_path_keeps_tool_chain_closed(tmp_path):
    tool = _DummyTool("dummy")
    provider = _StrictProvider(
        [
            LLMResponse(content="", tool_calls=[ToolCall("c1", "dummy", {"x": 1})]),
            LLMResponse(content="", tool_calls=[ToolCall("c2", "dummy", {"x": 1})]),
            LLMResponse(content="", tool_calls=[ToolCall("c3", "dummy", {"x": 1})]),
            LLMResponse(content="已总结当前进度", tool_calls=[]),
        ]
    )
    loop = _make_agent_loop(tmp_path, provider, tool)

    final, _, _, _vn, _ = asyncio.run(
        loop._run_agent_loop([{"role": "user", "content": "t"}])
    )

    assert "已总结" in final
    assert len(tool.calls) == 2


def test_subagent_loop_path_runs_mandatory_exit_with_closed_chain():
    tool = _DummyTool("dummy")
    exit_tool = _ExitTool("checkpoint")
    provider = _StrictProvider(
        [
            LLMResponse(content="", tool_calls=[ToolCall("s1", "dummy", {"x": 1})]),
            LLMResponse(content="", tool_calls=[ToolCall("s2", "dummy", {"x": 1})]),
            LLMResponse(content="", tool_calls=[ToolCall("s3", "dummy", {"x": 1})]),
            LLMResponse(
                content="",
                tool_calls=[ToolCall("e1", "checkpoint", {"note": "checkpoint"})],
            ),
            LLMResponse(content="当前进度已记录", tool_calls=[]),
        ]
    )
    subagent = SubAgent(
        provider=cast(Any, provider),
        model="m",
        tools=[tool, exit_tool],
        max_iterations=10,
        mandatory_exit_tools=["checkpoint"],
    )
    _install_tool_loop_guard(subagent)

    result = asyncio.run(subagent.run("do work"))

    assert subagent.last_exit_reason == "tool_loop"
    assert "记录" in result
    assert len(tool.calls) == 2
    assert exit_tool.called == 1
