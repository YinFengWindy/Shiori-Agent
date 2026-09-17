"""Role replies keep tools, state correction, and streaming within one turn."""

import json
from typing import Any, cast
from unittest.mock import AsyncMock

import pytest

from agent.core.passive_turn import DefaultReasoner
from agent.core.runtime_support import ToolDiscoveryState
from agent.looping.ports import LLMConfig, LLMServices
from agent.provider import LLMResponse, ToolCall
from agent.tool_hooks.base import ToolHook
from agent.tool_hooks.types import HookContext, HookOutcome
from agent.tools.base import Tool
from agent.tools.registry import ToolRegistry
from core.roles.reply_state import InvalidRoleReply


class CounterTool(Tool):
    name = "counter"
    description = "Count an external side effect"
    parameters = {"type": "object", "properties": {}}

    def __init__(self):
        self.calls = 0

    async def execute(self, **kwargs):
        self.calls += 1
        return "done"


def make_reasoner(provider, tools, *, max_iterations=5, tool_search_enabled=False):
    return DefaultReasoner(
        llm=LLMServices(
            provider=cast(Any, provider), light_provider=cast(Any, provider)
        ),
        llm_config=LLMConfig(max_iterations=max_iterations),
        tools=tools,
        discovery=ToolDiscoveryState(),
        tool_search_enabled=tool_search_enabled,
        memory_window=40,
    )


@pytest.mark.parametrize(
    "invalid",
    [
        "纯文本",
        "",
        '{"content":"回来啦"}',
        '{"content":"回来啦","mood":"未知","thought":"我放心了。"}',
    ],
)
async def test_tool_side_effect_runs_once_and_correction_streams_only_content(invalid):
    tool = CounterTool()
    tools = ToolRegistry()
    tools.register(tool, always_on=True)
    raw = json.dumps(
        {"content": "回来啦", "mood": "平静", "thought": "我终于放心了。"},
        ensure_ascii=False,
    )
    responses = [
        LLMResponse(content="", tool_calls=[ToolCall("c1", "counter", {})]),
        LLMResponse(content=invalid, thinking="mood 平静"),
        LLMResponse(content=raw),
    ]
    provider = AsyncMock()
    emitted = []

    async def chat(**kwargs):
        response = responses.pop(0)
        if kwargs.get("on_content_delta") and response.content:
            for char in response.content:
                await kwargs["on_content_delta"]({"content_delta": char})
        return response

    async def sink(delta):
        emitted.append(delta.get("content_delta", ""))

    provider.chat.side_effect = chat
    result = await make_reasoner(provider, tools).run(
        [{"role": "user", "content": "你好"}],
        reply_moods=("平静", "害羞"),
        on_content_delta=sink,
    )
    assert tool.calls == 1
    assert result.reply == raw
    assert result.streamed is True
    assert "".join(emitted) == "回来啦"
    assert len(provider.chat.call_args_list) == 3
    assert provider.chat.call_args.kwargs["tools"] == []
    assert all(
        call.kwargs["response_format"] == {"type": "json_object"}
        for call in provider.chat.call_args_list
    )


async def test_second_invalid_output_fails_instead_of_running_tools_again():
    provider = AsyncMock()
    provider.chat.side_effect = [
        LLMResponse(content="纯文本"),
        LLMResponse(content="还是纯文本"),
    ]
    with pytest.raises(InvalidRoleReply):
        await make_reasoner(provider, ToolRegistry()).run(
            [{"role": "user", "content": "你好"}], reply_moods=("平静",)
        )
    assert provider.chat.await_count == 2


async def test_transport_failure_after_tool_is_not_retried_as_format_error():
    provider = AsyncMock()
    provider.chat.side_effect = [
        LLMResponse(content="", tool_calls=[ToolCall("c1", "counter", {})]),
        TimeoutError("断流"),
    ]
    tools = ToolRegistry()
    tool = CounterTool()
    tools.register(tool, always_on=True)
    with pytest.raises(TimeoutError):
        await make_reasoner(provider, tools).run(
            [{"role": "user", "content": "你好"}], reply_moods=("平静",)
        )
    assert tool.calls == 1
    assert provider.chat.await_count == 2


async def test_iteration_summary_uses_formal_contract_without_routine_correction():
    provider = AsyncMock()
    raw = json.dumps(
        {
            "content": "查到了这些，余下稍后继续。",
            "mood": "平静",
            "thought": "我想先把现有结果告诉你。",
        },
        ensure_ascii=False,
    )
    provider.chat.side_effect = [
        LLMResponse(content="", tool_calls=[ToolCall("c1", "counter", {})]),
        LLMResponse(content=raw),
    ]
    tools = ToolRegistry()
    tool = CounterTool()
    tools.register(tool, always_on=True)
    result = await make_reasoner(provider, tools, max_iterations=1).run(
        [{"role": "user", "content": "你好"}], reply_moods=("平静",)
    )
    assert tool.calls == 1
    assert result.reply == raw
    assert provider.chat.await_count == 2
    request = provider.chat.call_args.kwargs
    assert request["response_format"] == {"type": "json_object"}
    assert "不要输出 JSON。" not in request["messages"][-1]["content"]


async def test_tool_response_content_is_not_persisted_as_dialogue_metadata():
    provider = AsyncMock()
    raw = json.dumps(
        {"content": "最终正文", "mood": "平静", "thought": "我放心了。"},
        ensure_ascii=False,
    )
    provider.chat.side_effect = [
        LLMResponse(content=raw, tool_calls=[ToolCall("c1", "counter", {})]),
        LLMResponse(content=raw),
    ]
    tools = ToolRegistry()
    tool = CounterTool()
    tools.register(tool, always_on=True)
    result = await make_reasoner(provider, tools).run(
        [{"role": "user", "content": "你好"}], reply_moods=("平静",)
    )
    assert tool.calls == 1
    assert result.reply == raw
    assert result.metadata["tool_chain"][0]["text"] == ""


class _OtherPluginFinalizeHook(ToolHook):
    """一个与 tool_loop_guard 毫无关系的 hook：身份、reason 措辞都不含
    "tool_loop_guard"。用来证明主回合的截断逻辑现在按结构化的
    ``HookOutcome.finalize`` 字段判断，而不是按插件名/ reason 字符串前缀嗅探
    （#239 验收标准 1、2）。"""

    name = "plugin:budget_watchdog:enforce"
    event = "pre_tool_use"

    def matches(self, ctx: HookContext) -> bool:
        return True

    async def run(self, ctx: HookContext) -> HookOutcome:
        return HookOutcome(
            decision="deny",
            reason="预算耗尽，其它插件也要求收尾",
            finalize=True,
        )


class _OtherPluginPlainDenyHook(ToolHook):
    """同样是"别的插件"，但只做普通 deny（不设置 finalize）。

    验收标准要求"普通 deny 仍保留原行为，不被误当成终止"：批次里的其余
    tool_call 应该继续逐个走 hook/执行，而不是被提前截断收尾。"""

    name = "plugin:budget_watchdog:plain_deny"
    event = "pre_tool_use"

    def matches(self, ctx: HookContext) -> bool:
        return True

    async def run(self, ctx: HookContext) -> HookOutcome:
        return HookOutcome(decision="deny", reason="该工具当前不允许调用")


async def test_finalize_denial_from_a_different_plugin_identity_truncates_the_batch():
    """AC1/AC2/AC3：任意插件身份的结构化收尾意图都能让主回合截断剩余批次，
    并进入既有总结流程；不再要求 hook 名或 reason 里出现 "tool_loop_guard"。"""
    tool = CounterTool()
    tools = ToolRegistry()
    tools.register(tool, always_on=True)
    provider = AsyncMock()
    provider.chat.side_effect = [
        LLMResponse(
            content="",
            tool_calls=[ToolCall("c1", "counter", {}), ToolCall("c2", "counter", {})],
        ),
        LLMResponse(content="收尾总结"),
    ]
    reasoner = make_reasoner(provider, tools)
    reasoner.add_tool_hooks([_OtherPluginFinalizeHook()])

    result = await reasoner.run([{"role": "user", "content": "test"}])

    # c1 被拒绝且从未真正执行；c2 因收尾被直接跳过，压根没有进过 hook/执行器。
    assert tool.calls == 0
    assert len(result.invocations) == 1
    assert result.invocations[0].id == "c1"
    assert result.metadata["tool_chain"][0]["calls"][0]["status"] == "denied"
    # 没有第三次"正常继续"的 LLM 调用：第二次调用就是收尾总结。
    assert provider.chat.await_count == 2
    assert result.reply == "收尾总结"


async def test_finalize_denial_from_a_different_plugin_identity_truncates_the_preflight_branch():
    """同一份验收标准，覆盖另一条独立代码路径：deferred/unlocked 工具走的是
    ``ToolExecutor.preflight``（reasoning_loop.py 里紧跟 "6.1 deferred 工具未
    解锁" 那段），跟已执行工具的 ``execute`` 分支是两处完全独立的判断/截断
    代码。只测过 execute 分支不能证明 preflight 分支也不再按插件身份判断——
    这里用 tool_search_enabled=True + 一个未 always_on 的工具，逼 LLM 直接
    调用一个尚未解锁的工具名，触发 preflight 分支。"""
    tool = CounterTool()
    tool.name = "hidden_tool"
    tools = ToolRegistry()
    tools.register(tool)  # 不带 always_on：在 visible_names 之外，走 preflight
    provider = AsyncMock()
    provider.chat.side_effect = [
        LLMResponse(
            content="",
            tool_calls=[
                ToolCall("c1", "hidden_tool", {}),
                ToolCall("c2", "hidden_tool", {}),
            ],
        ),
        LLMResponse(content="收尾总结"),
    ]
    reasoner = make_reasoner(provider, tools, tool_search_enabled=True)
    reasoner.add_tool_hooks([_OtherPluginFinalizeHook()])

    result = await reasoner.run([{"role": "user", "content": "test"}])

    assert tool.calls == 0
    assert len(result.invocations) == 1
    assert result.invocations[0].id == "c1"
    assert result.metadata["tool_chain"][0]["calls"][0]["status"] == "denied"
    assert provider.chat.await_count == 2
    assert result.reply == "收尾总结"


async def test_plain_deny_without_finalize_does_not_truncate_the_batch():
    """回归防护：只是 finalize=False 的普通 deny，批次里的其余工具调用必须
    继续正常执行/被逐个拒绝，回合本身也应正常推进到下一轮 LLM 调用，而不是
    被误判成收尾。"""
    tool = CounterTool()
    tools = ToolRegistry()
    tools.register(tool, always_on=True)
    provider = AsyncMock()
    provider.chat.side_effect = [
        LLMResponse(
            content="",
            tool_calls=[ToolCall("c1", "counter", {}), ToolCall("c2", "counter", {})],
        ),
        LLMResponse(content="最终回复"),
    ]
    reasoner = make_reasoner(provider, tools)
    reasoner.add_tool_hooks([_OtherPluginPlainDenyHook()])

    result = await reasoner.run([{"role": "user", "content": "test"}])

    # 两次调用都被拒绝（工具本身没有真正执行），但两者都被处理了，没有被跳过。
    assert tool.calls == 0
    assert len(result.invocations) == 2
    assert [call.id for call in result.invocations] == ["c1", "c2"]
    calls = result.metadata["tool_chain"][0]["calls"]
    assert [c["status"] for c in calls] == ["denied", "denied"]
    # 回合正常推进到了下一轮 LLM 调用，而不是提前收尾。
    assert provider.chat.await_count == 2
    assert result.reply == "最终回复"
