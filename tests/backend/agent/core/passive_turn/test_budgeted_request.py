"""Only budget failures are owned by the request boundary; others keep their type."""

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from agent.core.passive_turn.budgeted_request import budgeted_chat
from agent.core.passive_turn.compaction import (
    RequestCompaction,
    request_compaction_scope,
)
from agent.prompting.input_budget import BudgetPolicy
from agent.prompting.usage_accounting import turn_usage
from agent.prompting.usage_anchor import usage_context
from agent.provider import LLMProvider
from core.compaction import CompactionController, CompactionPolicy


@pytest.mark.parametrize("business_call", [False, True])
async def test_minimal_request_keeps_reply_schema_but_rejects_business_calls(
    memory_harness, business_call
):
    from agent.core.passive_turn.natural_reply import finish_reply_schema
    from agent.provider import LLMResponse, ToolCall
    from core.compaction import CompactionFailedError

    h = memory_harness
    session = h.manager.get_or_create("cli:minimal-reply")
    provider = LLMProvider(api_key="test", max_retries=0)
    provider.chat = AsyncMock(
        return_value=LLMResponse(
            content="",
            tool_calls=[
                ToolCall(
                    "reply",
                    "counter" if business_call else "finish_reply",
                    {"messages": ["完成"]},
                )
            ],
        )
    )
    controller = CompactionController(
        h.manager,
        h.maintenance,
        SimpleNamespace(model_name="m", generate=AsyncMock()),
    )
    scope = RequestCompaction(
        controller,
        session.key,
        None,
        CompactionPolicy(),
        0,
        1,
        AsyncMock(),
        lambda _: [],
    )
    scope.degraded = True
    reply_tool = finish_reply_schema()
    schemas = [{"type": "function", "function": {"name": "counter"}}]
    try:
        with request_compaction_scope(scope):
            request = budgeted_chat(
                provider,
                messages=[{"role": "user", "content": "当前任务"}],
                tools=schemas,
                reply_tool=reply_tool,
                model="m",
                max_tokens=100,
            )
            if business_call:
                with pytest.raises(CompactionFailedError):
                    await request
            else:
                result = await request
                assert result.tool_calls[0].name == "finish_reply"
        assert provider.chat.call_args.kwargs["tools"] == [reply_tool]
        assert schemas == [reply_tool]
    finally:
        await provider.aclose()


@pytest.mark.parametrize(
    ("error", "record_fails"),
    [
        (OSError("network unavailable"), False),
        (asyncio.TimeoutError(), False),
        (OSError("network unavailable"), True),
    ],
)
async def test_ordinary_provider_failure_keeps_type_and_last_compaction(
    memory_harness, error, record_fails
):
    h = memory_harness
    session = h.manager.get_or_create("cli:ordinary-failure")
    provider = LLMProvider(
        api_key="test",
        model_context_window=100000,
        default_max_tokens=100,
        budget_policy=BudgetPolicy(safety_margin_tokens=100),
    )
    provider._create_with_retry = AsyncMock(side_effect=error)
    controller = CompactionController(
        h.manager,
        h.maintenance,
        SimpleNamespace(model_name="m", generate=AsyncMock()),
    )
    scope = RequestCompaction(
        controller,
        session.key,
        None,
        CompactionPolicy(),
        0,
        2,
        AsyncMock(),
        lambda _: [],
    )
    if record_fails:
        # A broken observation must not mask the provider error.
        controller.record = AsyncMock(side_effect=RuntimeError("record broken"))
    messages = [
        {"role": "system", "content": "constraints"},
        {"role": "user", "content": "current"},
    ]
    try:
        with (
            turn_usage(),
            usage_context((session.key,)),
            request_compaction_scope(scope),
        ):
            with pytest.raises(type(error)) as caught:
                await budgeted_chat(
                    provider, messages=messages, tools=[], model="m", max_tokens=100
                )
        assert caught.value is error
        if record_fails:
            return
        assert controller.latest(session.key, None) is None
        request = controller.latest(session.key, None, request=True)
        assert request is not None and request["phase"] == "request"
        assert request["failure_kind"] == "provider_error"
    finally:
        await provider.aclose()
