from tests.support.tool_hooks import _shared_http_resources as _shared_http_resources
from tests.support.tool_hooks import (
    _DummyTool,
    _FakeProvider,
    _StrictProvider,
    _ExitTool,
    _install_tool_loop_guard,
)
from agent.provider import LLMResponse, ToolCall
from agent.subagent import SubAgent
from typing import Any, cast
import asyncio


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
