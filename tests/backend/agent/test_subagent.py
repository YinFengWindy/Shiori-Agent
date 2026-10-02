"""SubAgent 消费结构化收尾契约做批量截断（#239）。

与 ``tests/backend/agent/core/passive_turn/test_reasoning_loop.py`` 的两个
finalize 测试成对：那边覆盖主回合，这里覆盖子 Agent 路径，用同一对
"别的插件身份" hook 证明两条消费路径都不再按插件名/ reason 字符串前缀
判断是否收尾。
"""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock

import pytest

from agent.provider import LLMResponse, ToolCall
from agent.subagent import SubAgent
from agent.tool_hooks.base import ToolHook
from agent.tool_hooks.types import HookContext
from shiori_sdk.tool_hooks import HookOutcome
from shiori_sdk.tools import Tool


class _CounterTool(Tool):
    name = "counter"
    description = "count calls"
    parameters: dict[str, Any] = {"type": "object", "properties": {}}

    def __init__(self) -> None:
        self.calls = 0

    async def execute(self, **kwargs: Any) -> str:
        self.calls += 1
        return "done"


class _OtherPluginFinalizeHook(ToolHook):
    """与 tool_loop_guard 无关的插件身份：hook 名、reason 都不含
    "tool_loop_guard"，只靠 ``HookOutcome.finalize=True`` 表达收尾意图。"""

    name = "plugin:budget_watchdog:enforce"
    event = "pre_tool_use"

    def matches(self, ctx: HookContext) -> bool:
        return True

    async def run(self, ctx: HookContext) -> HookOutcome:
        return HookOutcome(decision="deny", reason="预算耗尽，要求收尾", finalize=True)


class _OtherPluginPlainDenyHook(ToolHook):
    """同样是别的插件，但只做普通 deny（不设置 finalize），必须保持原行为。"""

    name = "plugin:budget_watchdog:plain_deny"
    event = "pre_tool_use"

    def matches(self, ctx: HookContext) -> bool:
        return True

    async def run(self, ctx: HookContext) -> HookOutcome:
        return HookOutcome(decision="deny", reason="该工具当前不允许调用")


async def test_finalize_denial_from_a_different_plugin_truncates_subagent_batch():
    """AC3：子 Agent 路径下，任意插件身份的结构化收尾意图都能截断剩余批次并
    进入既有的 last_exit_reason="tool_loop" + 收尾总结流程。"""
    tool = _CounterTool()
    provider = AsyncMock()
    provider.chat.side_effect = [
        LLMResponse(
            content="",
            tool_calls=[ToolCall("c1", "counter", {}), ToolCall("c2", "counter", {})],
        ),
        LLMResponse(content="收尾总结"),
    ]
    subagent = SubAgent(provider=provider, model="test-model", tools=[tool])
    subagent.add_tool_hooks([_OtherPluginFinalizeHook()])

    result = await subagent.run("do the thing")

    # c1 被拒绝，从未真正执行；c2 因收尾被跳过，压根没有进过 hook/执行器。
    assert tool.calls == 0
    assert subagent.last_exit_reason == "tool_loop"
    assert result == "收尾总结"
    assert provider.chat.await_count == 2
    main_call, summary_call = provider.chat.await_args_list
    assert main_call.kwargs.get("call_purpose", "default") == "default"
    assert summary_call.kwargs["call_purpose"] == "auxiliary"
    assert summary_call.kwargs["max_tokens"] == 512


async def test_plain_deny_without_finalize_does_not_truncate_subagent_batch():
    """回归防护：普通 deny（finalize 默认 False）保持原行为——批次里的每个
    调用仍然逐个走 hook，任务正常推进到下一轮，不会被误判成收尾。"""
    tool = _CounterTool()
    provider = AsyncMock()
    provider.chat.side_effect = [
        LLMResponse(
            content="",
            tool_calls=[ToolCall("c1", "counter", {}), ToolCall("c2", "counter", {})],
        ),
        LLMResponse(content="最终结果"),
    ]
    subagent = SubAgent(provider=provider, model="test-model", tools=[tool])
    subagent.add_tool_hooks([_OtherPluginPlainDenyHook()])

    result = await subagent.run("do the thing")

    assert tool.calls == 0
    assert subagent.last_exit_reason == "completed"
    assert result == "最终结果"
    assert provider.chat.await_count == 2


@pytest.mark.parametrize("max_tokens,expected_budget", [(256, 256), (8192, 512)])
async def test_forced_final_summary_is_auxiliary_with_a_bounded_budget(
    max_tokens, expected_budget
):
    provider = AsyncMock()
    provider.chat.side_effect = [
        LLMResponse(content="", tool_calls=[ToolCall("c1", "counter", {})]),
        LLMResponse(content="工具结果已整理。"),
    ]
    subagent = SubAgent(
        provider=provider,
        model="test-model",
        tools=[_CounterTool()],
        max_iterations=1,
        max_tokens=max_tokens,
    )

    result = await subagent.run("do the thing")

    assert result == "工具结果已整理。"
    assert subagent.last_exit_reason == "forced_summary"
    summary_call = provider.chat.await_args
    assert summary_call.kwargs["call_purpose"] == "auxiliary"
    assert summary_call.kwargs["max_tokens"] == expected_budget


@pytest.mark.parametrize("background", [False, True], ids=["awaited", "runtime-task"])
async def test_child_visible_request_and_usage_never_replace_parent(background):
    import asyncio
    from types import SimpleNamespace
    from agent.provider import LLMProvider
    from agent.prompting.usage_anchor import usage_context
    from agent.prompting.usage_accounting import current_usage, turn_usage
    from core.common.runtime_tasks import create_runtime_task

    provider = LLMProvider(
        api_key="test", model_context_window=128000, default_max_tokens=8192
    )
    child_started, child_release = asyncio.Event(), asyncio.Event()

    async def create(kwargs, **unused):
        child = kwargs["messages"][-1]["content"] == "child-visible-task"
        if child and background:
            child_started.set()
            await child_release.wait()
        return SimpleNamespace(
            choices=[
                SimpleNamespace(
                    message=SimpleNamespace(content="done", tool_calls=[]),
                    finish_reason="stop",
                )
            ],
            usage=SimpleNamespace(
                prompt_tokens=7 if child else 1000,
                completion_tokens=2,
                total_tokens=9 if child else 1002,
            ),
        )

    provider._create_with_retry = create
    agent = SubAgent(provider=provider, model="same-model", tools=[])
    request = dict(
        messages=[{"role": "user", "content": "parent-visible-context"}],
        tools=[],
        model="same-model",
        max_tokens=8192,
    )
    try:
        with usage_context(("role:a", "user", "")), turn_usage():
            if background:
                child = create_runtime_task(
                    agent.run("child-visible-task"), name="usage-isolation-test"
                )
                await child_started.wait()
                # Parent response arrives first; child finishes during a later await.
                await provider.chat(**request)
                child_release.set()
                assert await child == "done"
            else:
                await provider.chat(**request)
                assert await agent.run("child-visible-task") == "done"
            budget = provider.input_budget(**request)
            assert budget is not None
            assert budget.estimate.source == "actual"
            assert budget.estimate.tokens == 1000
            parent = current_usage()
            assert parent["last_request"]["prompt_tokens"] == 1000
            assert parent["cumulative"]["prompt_tokens"] == 1000
            assert len(parent["calls"]) == 1
            assert agent.last_usage["last_request"]["prompt_tokens"] == 7
            assert agent.last_usage["cumulative"]["prompt_tokens"] == 7
        # One-off child anchors never accumulate in the shared provider store.
        assert len(provider._usage_anchors._anchors) == 1
    finally:
        await provider.aclose()
