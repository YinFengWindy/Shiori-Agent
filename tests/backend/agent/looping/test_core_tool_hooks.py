from shiori_plugin_testkit.memory import FakeMemoryEngine
from agent.looping.core import AgentLoop
from agent.looping.ports import (
    AgentLoopConfig,
    AgentLoopDeps,
    LLMConfig,
    MemoryServices,
)
from tests.support.tool_hooks import _shared_http_resources as _shared_http_resources
from tests.support.tool_hooks import (
    _DummyTool,
    _FakeProvider,
    _StrictProvider,
    _make_agent_loop_with_tools,
    _make_agent_loop,
)
from agent.provider import LLMResponse, ToolCall
from agent.tools.registry import ToolRegistry
from unittest.mock import MagicMock
from typing import Any, cast
import asyncio


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
