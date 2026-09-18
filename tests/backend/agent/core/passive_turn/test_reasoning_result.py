"""Auxiliary budget summaries remain separate from role-facing replies."""

from unittest.mock import AsyncMock

import pytest

from agent.core.passive_turn import DefaultReasoner
from agent.core.runtime_support import ToolDiscoveryState
from agent.looping.ports import LLMConfig, LLMServices
from agent.provider import LLMResponse
from agent.tools.registry import ToolRegistry


async def test_role_summary_normalizes_legacy_content_before_mood_call():
    provider = AsyncMock()
    provider.chat.side_effect = [
        LLMResponse(
            content='{"thought":"我想先收尾。","content":"先告诉你当前进度。","mood":"害羞"}',
            total_tokens=40,
        ),
        LLMResponse(content='{"mood":"平静","thought":"我已经告诉你进度。"}'),
    ]
    reasoner = DefaultReasoner(
        llm=LLMServices(provider=provider, light_provider=provider),
        llm_config=LLMConfig(),
        tools=ToolRegistry(),
        discovery=ToolDiscoveryState(),
        tool_search_enabled=False,
        memory_window=40,
    )

    content, tokens, role_reply = await reasoner._summarize_incomplete_progress(
        [{"role": "user", "content": "请检查"}],
        reason="max_iterations",
        iteration=1,
        tools_used=["search"],
        reply_moods=("平静", "害羞"),
    )

    assert content == "先告诉你当前进度。"
    assert tokens == 40
    assert role_reply is not None
    assert role_reply.content == content
    assert role_reply.mood == "平静"
    assert provider.chat.call_args_list[1].kwargs["messages"][-2] == {
        "role": "assistant",
        "content": content,
    }


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
