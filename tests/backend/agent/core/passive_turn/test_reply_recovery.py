"""Summary completions reject tool calls while ordinary loop steps can dispatch them."""

from unittest.mock import AsyncMock
from types import SimpleNamespace

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


async def test_local_recovery_compaction_selects_tools_free_prompt_before_sending(
    memory_harness,
):
    from agent.core.passive_turn.compaction import (
        RequestCompaction,
        request_compaction_scope,
    )
    from agent.prompting.input_budget import BudgetPolicy
    from agent.prompting.usage_accounting import turn_usage
    from agent.provider import LLMProvider
    from core.compaction import CompactionController, CompactionPolicy
    from core.compaction_summary import WorkingSummary

    h = memory_harness
    session = h.manager.get_or_create("cli:recovery-preflight")
    session.metadata["role_id"] = "mira"
    session.add_message("user", "old task")
    session.add_message("assistant", "noted")
    h.manager.save(session)
    messages = [
        {"role": "system", "content": "optional " * 3000},
        {"role": "user", "content": "current task"},
    ]
    minimal = [{"role": "system", "content": "constraints"}, messages[1]]
    tools = [
        {
            "type": "function",
            "function": {
                "name": "counter",
                "description": "catalog " * 3000,
                "parameters": {"type": "object", "properties": {}},
            },
        }
    ]
    provider = LLMProvider(
        api_key="test",
        model_context_window=2000,
        default_max_tokens=100,
        budget_policy=BudgetPolicy(safety_margin_tokens=20),
    )
    transport = AsyncMock(
        return_value=SimpleNamespace(
            choices=[
                SimpleNamespace(
                    message=SimpleNamespace(content="尚未取得结果。", tool_calls=[]),
                    finish_reason="stop",
                )
            ],
            usage=None,
        )
    )
    provider._create_with_retry = transport
    controller = CompactionController(
        h.manager,
        h.maintenance,
        SimpleNamespace(
            model_name="m",
            generate=AsyncMock(
                side_effect=lambda prepared: WorkingSummary(
                    "no results yet", prepared.removed_message_ids
                )
            ),
        ),
    )
    scope = RequestCompaction(
        controller,
        session.key,
        None,
        CompactionPolicy(0),
        2,
        2,
        AsyncMock(return_value=messages),
        lambda _: [],
        render_minimal=AsyncMock(return_value=minimal),
    )
    try:
        with request_compaction_scope(scope), turn_usage():
            completion = await complete_reply(
                LLMResponse(content=""),
                output=RoleReplyOutput(None, enabled=False),
                messages=messages,
                provider=provider,
                model="m",
                max_tokens=100,
                role_reply=False,
                session=session.key,
                channel="cli",
                iteration=1,
                allow_tool_calls=True,
                tools=tools,
            )
        assert scope.degraded and tools == []
        assert completion.response.content == "尚未取得结果。"
        transport.assert_awaited_once()
        request = transport.await_args.args[0]
        assert not request.get("tools")
        assert "请根据已有结果直接回复用户" in request["messages"][-1]["content"]
        assert "尚未取得的信息请明确说明" in request["messages"][-1]["content"]
        assert scope.prefix_length == len(messages) == 2
    finally:
        await provider.aclose()
