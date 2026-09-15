"""Role replies keep tools, state correction, and streaming within one turn."""

import json
from typing import Any, cast
from unittest.mock import AsyncMock

import pytest

from agent.core.passive_turn import DefaultReasoner
from agent.core.runtime_support import ToolDiscoveryState
from agent.looping.ports import LLMConfig, LLMServices
from agent.provider import LLMResponse, ToolCall
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


def make_reasoner(provider, tools, *, max_iterations=5):
    return DefaultReasoner(
        llm=LLMServices(
            provider=cast(Any, provider), light_provider=cast(Any, provider)
        ),
        llm_config=LLMConfig(max_iterations=max_iterations),
        tools=tools,
        discovery=ToolDiscoveryState(),
        tool_search_enabled=False,
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
