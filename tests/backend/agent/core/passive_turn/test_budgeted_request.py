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


@pytest.mark.parametrize(
    "error", [OSError("network unavailable"), asyncio.TimeoutError()]
)
async def test_ordinary_provider_failure_keeps_type_and_last_compaction(
    memory_harness, error
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
            with pytest.raises(type(error)):
                await budgeted_chat(
                    provider, messages=messages, tools=[], model="m", max_tokens=100
                )
        assert controller.latest(session.key, None) is None
        request = controller.latest(session.key, None, request=True)
        assert request is not None and request["phase"] == "request"
        assert request["failure_kind"] == "provider_error"
    finally:
        await provider.aclose()
