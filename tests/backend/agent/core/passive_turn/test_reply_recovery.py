"""Summary completions reject tool calls while ordinary loop steps can dispatch them."""

from unittest.mock import AsyncMock

import pytest

from agent.core.passive_turn.empty_reply import EmptyReplyError
from agent.core.passive_turn.reply_recovery import complete_reply
from agent.core.reply_output import RoleReplyOutput
from agent.provider import LLMResponse, ToolCall


@pytest.mark.parametrize("allow_tool_calls", [False, True])
async def test_tools_are_only_returned_to_an_explicit_dispatching_caller(
    allow_tool_calls,
):
    provider = AsyncMock()
    response = LLMResponse(content="", tool_calls=[ToolCall("t1", "counter", {})])
    operation = complete_reply(
        response,
        output=RoleReplyOutput(None, enabled=True),
        messages=[],
        provider=provider,
        model="m",
        max_tokens=512,
        role_reply=True,
        session="role:mira",
        channel="qq",
        iteration=1,
        allow_tool_calls=allow_tool_calls,
    )
    if allow_tool_calls:
        result = await operation
        assert result.response is response
        assert result.diagnostics is None
    else:
        with pytest.raises(EmptyReplyError) as caught:
            await operation
        assert caught.value.diagnostics["outcome"] == "unexpected_tool_calls"
        assert caught.value.diagnostics["retries"] == 0
    provider.chat.assert_not_awaited()


@pytest.mark.parametrize(
    "tool_choice", ["auto", {"type": "function", "function": {"name": "counter"}}]
)
async def test_recovery_preserves_current_schema_and_tool_choice(tool_choice):
    tools = [{"type": "function", "function": {"name": "counter"}}]
    provider = AsyncMock()
    provider.chat.return_value = LLMResponse(
        content="", tool_calls=[ToolCall("t1", "counter", {})]
    )
    messages = [{"role": "user", "content": "continue task"}]
    result = await complete_reply(
        LLMResponse(content=""),
        output=RoleReplyOutput(None, enabled=False),
        messages=messages,
        provider=provider,
        model="m",
        max_tokens=512,
        role_reply=False,
        session="cli:test",
        channel="cli",
        iteration=1,
        allow_tool_calls=True,
        tools=tools,
        tool_choice=tool_choice,
    )
    request = provider.chat.await_args.kwargs
    assert request["tools"] is tools
    assert request["messages"][:-2] == messages
    assert request["tool_choice"] == tool_choice
    assert result.response.tool_calls[0].name == "counter"
    assert result.diagnostics["outcome"] == "recovered"


@pytest.mark.parametrize(
    "allow_tool_calls,tool_choice", [(False, "auto"), (True, "none")]
)
async def test_tool_disabled_recovery_rejects_unsolicited_calls(
    allow_tool_calls, tool_choice
):
    provider = AsyncMock()
    provider.chat.return_value = LLMResponse(
        content="", tool_calls=[ToolCall("t1", "counter", {})]
    )
    with pytest.raises(EmptyReplyError) as caught:
        await complete_reply(
            LLMResponse(content=""),
            output=RoleReplyOutput(None, enabled=False),
            messages=[],
            provider=provider,
            model="m",
            max_tokens=512,
            role_reply=False,
            session="cli:test",
            channel="cli",
            iteration=1,
            allow_tool_calls=allow_tool_calls,
            tools=[{"type": "function", "function": {"name": "counter"}}],
            tool_choice=tool_choice,
        )
    assert caught.value.diagnostics["outcome"] == "unexpected_tool_calls"
