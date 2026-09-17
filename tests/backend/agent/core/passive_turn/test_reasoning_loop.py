"""Role replies stream plain content; mood/thought are fetched separately.

Issue #303: the old contract asked the model to wrap `{content, mood,
thought}` as one JSON object. Real dialogue is full of quotes, newlines, and
parenthetical asides, so the model routinely produced unescaped ASCII double
quotes that closed the JSON early and failed the whole turn. These tests
assert the replacement contract: content streams as plain text with no JSON
wrapper and no format-correction retry, and mood/thought come from one
separate `disable_thinking` call afterward that degrades quietly on failure.
"""

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


def mood_payload(mood="平静", thought="我终于放心了。") -> str:
    import json

    return json.dumps({"mood": mood, "thought": thought}, ensure_ascii=False)


def streaming_chat(responses: list[LLMResponse]):
    """A provider.chat stand-in that streams each response's content when a
    live sink is given, mirroring real provider streaming behaviour."""

    async def chat(**kwargs):
        response = responses.pop(0)
        sink = kwargs.get("on_content_delta")
        if sink and response.content:
            for char in response.content:
                await sink({"content_delta": char})
        return response

    return chat


async def test_content_with_quotes_newlines_and_emoji_delivers_without_json_wrapper():
    """The exact defect pattern from #303: unescaped quotes, a parenthetical
    aside, a newline, and an emoji must all reach delivery intact."""
    content = '她说："稍等一下"。\n（转身离开）🌸'
    provider = AsyncMock()
    provider.chat.side_effect = streaming_chat(
        [LLMResponse(content=content), LLMResponse(content=mood_payload())]
    )
    emitted: list[str] = []

    async def sink(delta):
        emitted.append(delta.get("content_delta", ""))

    result = await make_reasoner(provider, ToolRegistry()).run(
        [{"role": "user", "content": "你好"}],
        reply_moods=("平静", "害羞"),
        on_content_delta=sink,
    )

    assert result.reply == content
    assert "".join(emitted) == content
    assert provider.chat.await_count == 2
    main_call, mood_call = provider.chat.call_args_list
    assert "response_format" not in main_call.kwargs
    assert mood_call.kwargs["disable_thinking"] is True
    assert mood_call.kwargs["response_format"] == {"type": "json_object"}
    role_reply = result.metadata["role_reply"]
    assert role_reply.content == content
    assert role_reply.mood == "平静"
    assert result.metadata["role_reply_mood_fresh"] is True


async def test_mood_fetch_reuses_the_reply_prefix_with_produced_content():
    provider = AsyncMock()
    provider.chat.side_effect = [
        LLMResponse(content="回来啦"),
        LLMResponse(content=mood_payload()),
    ]
    await make_reasoner(provider, ToolRegistry()).run(
        [{"role": "user", "content": "你好"}],
        reply_moods=("平静",),
    )
    mood_call = provider.chat.call_args_list[1]
    mood_messages = mood_call.kwargs["messages"]
    assert mood_messages[0] == {"role": "user", "content": "你好"}
    assert mood_messages[1] == {"role": "assistant", "content": "回来啦"}


async def test_mood_fetch_failure_degrades_without_failing_delivery():
    provider = AsyncMock()
    provider.chat.side_effect = [
        LLMResponse(content="正文照常送达"),
        TimeoutError("断流"),
    ]
    result = await make_reasoner(provider, ToolRegistry()).run(
        [{"role": "user", "content": "你好"}],
        reply_moods=("平静",),
        previous_mood="害羞",
        previous_thought="我在等你。",
    )
    assert result.reply == "正文照常送达"
    assert provider.chat.await_count == 2
    role_reply = result.metadata["role_reply"]
    assert role_reply.content == "正文照常送达"
    assert role_reply.mood == "害羞"
    assert role_reply.thought == "我在等你。"
    assert result.metadata["role_reply_mood_fresh"] is False


async def test_mood_fetch_never_overwrites_main_response_thinking():
    """The mood call's own thinking (if any leaks through) must never replace
    the main call's `response.thinking`, which stays the only reasoning
    source for this turn (issue #300 regression guard)."""
    provider = AsyncMock()
    provider.chat.side_effect = [
        LLMResponse(content="正文", thinking="主线思考"),
        LLMResponse(content=mood_payload(), thinking="心情调用产生的思考"),
    ]
    result = await make_reasoner(provider, ToolRegistry()).run(
        [{"role": "user", "content": "你好"}],
        reply_moods=("平静",),
    )
    assert result.thinking == "主线思考"


async def test_tool_call_precedes_plain_final_reply_without_format_correction():
    tool = CounterTool()
    tools = ToolRegistry()
    tools.register(tool, always_on=True)
    provider = AsyncMock()
    provider.chat.side_effect = [
        LLMResponse(content="", tool_calls=[ToolCall("c1", "counter", {})]),
        LLMResponse(content="查到了，稍等"),
        LLMResponse(content=mood_payload()),
    ]
    result = await make_reasoner(provider, tools).run(
        [{"role": "user", "content": "你好"}],
        reply_moods=("平静",),
    )
    assert tool.calls == 1
    assert result.reply == "查到了，稍等"
    assert provider.chat.await_count == 3


async def test_transport_failure_after_tool_call_propagates_without_retry():
    provider = AsyncMock()
    tools = ToolRegistry()
    tool = CounterTool()
    tools.register(tool, always_on=True)
    provider.chat.side_effect = [
        LLMResponse(content="", tool_calls=[ToolCall("c1", "counter", {})]),
        TimeoutError("断流"),
    ]
    with pytest.raises(TimeoutError):
        await make_reasoner(provider, tools).run(
            [{"role": "user", "content": "你好"}], reply_moods=("平静",)
        )
    assert tool.calls == 1
    assert provider.chat.await_count == 2


async def test_content_beside_tool_calls_without_a_live_consumer_reaches_tool_chain():
    """A model's lead-in before deciding to call a tool ("我查一下…") is kept
    in the tool chain exactly like a non-role turn's; there is nothing left to
    zero out, since content is plain text with no JSON envelope to strip."""
    provider = AsyncMock()
    tools = ToolRegistry()
    tool = CounterTool()
    tools.register(tool, always_on=True)
    provider.chat.side_effect = [
        LLMResponse(content="顺带说的话", tool_calls=[ToolCall("c1", "counter", {})]),
        LLMResponse(content="最终正文"),
        LLMResponse(content=mood_payload()),
    ]
    result = await make_reasoner(provider, tools).run(
        [{"role": "user", "content": "你好"}], reply_moods=("平静",)
    )
    assert tool.calls == 1
    assert result.reply == "最终正文"
    assert result.metadata["tool_chain"][0]["text"] == "顺带说的话"


async def test_prelude_content_streamed_live_then_tool_call_completes_normally():
    """Issue #303 regression: a model narrating before calling a tool ("我查
    一下历史再回你") streams that lead-in through the same content-delta
    channel as a final reply, so it can no longer be told apart from "already
    spoken final content" - the #286-era guard that failed the turn here had
    no valid signal left to key off and must not resurrect. The turn should
    stream the lead-in, run the tool, and still deliver a final reply."""
    tools = ToolRegistry()
    tool = CounterTool()
    tools.register(tool, always_on=True)
    provider = AsyncMock()
    provider.chat.side_effect = streaming_chat(
        [
            LLMResponse(content="说到一半", tool_calls=[ToolCall("c1", "counter", {})]),
            LLMResponse(content="最终正文"),
            LLMResponse(content=mood_payload()),
        ]
    )
    emitted: list[str] = []

    async def sink(delta):
        emitted.append(delta.get("content_delta", ""))

    result = await make_reasoner(provider, tools).run(
        [{"role": "user", "content": "你好"}],
        reply_moods=("平静",),
        on_content_delta=sink,
    )
    assert "".join(emitted) == "说到一半最终正文"
    assert tool.calls == 1
    assert result.reply == "最终正文"
    assert result.metadata["tool_chain"][0]["text"] == "说到一半"


async def test_iteration_summary_fetches_mood_without_json_content_contract():
    provider = AsyncMock()
    provider.chat.side_effect = [
        LLMResponse(content="", tool_calls=[ToolCall("c1", "counter", {})]),
        LLMResponse(content="查到了这些，余下稍后继续。"),
        LLMResponse(content=mood_payload(thought="我想先把现有结果告诉你。")),
    ]
    tools = ToolRegistry()
    tool = CounterTool()
    tools.register(tool, always_on=True)
    result = await make_reasoner(provider, tools, max_iterations=1).run(
        [{"role": "user", "content": "你好"}], reply_moods=("平静",)
    )
    assert tool.calls == 1
    assert result.reply == "查到了这些，余下稍后继续。"
    assert provider.chat.await_count == 3
    summary_call, mood_call = provider.chat.call_args_list[1:]
    assert "response_format" not in summary_call.kwargs
    assert "不要输出 JSON" in summary_call.kwargs["messages"][-1]["content"]
    assert mood_call.kwargs["disable_thinking"] is True
    role_reply = result.metadata["role_reply"]
    assert role_reply.content == "查到了这些，余下稍后继续。"
    assert role_reply.thought == "我想先把现有结果告诉你。"
    assert result.metadata["role_reply_mood_fresh"] is True


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
