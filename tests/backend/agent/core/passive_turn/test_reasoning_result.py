"""Auxiliary budget summaries remain separate from role-facing replies."""

from unittest.mock import AsyncMock

import pytest

from agent.core.passive_turn import DefaultReasoner
from agent.core.runtime_support import ToolDiscoveryState
from agent.looping.ports import LLMConfig, LLMServices
from agent.provider import LLMResponse
from agent.tools.registry import ToolRegistry


@pytest.mark.parametrize("max_tokens,expected_budget", [(256, 256), (8192, 512)])
async def test_internal_budget_summary_uses_auxiliary_purpose(
    max_tokens, expected_budget
):
    provider = AsyncMock()
    provider.chat.return_value = LLMResponse(
        content="检查到当前进度。", total_tokens=40
    )
    reasoner = DefaultReasoner(
        llm=LLMServices(provider=provider, light_provider=provider),
        llm_config=LLMConfig(max_tokens=max_tokens),
        tools=ToolRegistry(),
        discovery=ToolDiscoveryState(),
        tool_search_enabled=False,
        memory_window=40,
    )

    result = await reasoner._summarize_incomplete_progress(
        [{"role": "user", "content": "请检查"}],
        reason="max_iterations",
        iteration=1,
        tools_used=["search"],
    )

    assert result == ("检查到当前进度。", 40, None)
    request = provider.chat.await_args.kwargs
    assert request["call_purpose"] == "auxiliary"
    assert request["max_tokens"] == expected_budget
    assert request["tools"] == []
