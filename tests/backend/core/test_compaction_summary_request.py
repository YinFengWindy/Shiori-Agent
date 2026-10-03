"""Every summary request, including shortening, must fit before reaching transport."""

import json
from types import SimpleNamespace
from unittest.mock import AsyncMock
import pytest
from agent.provider import LLMProvider, LLMResponse
from agent.prompting.output_usage import parse_output_usage
from core.compaction_summary_request import SummaryRequest
from core.compaction_summary_validation import SUMMARY_FIELDS


async def test_shortening_input_overflow_keeps_first_attempt_and_does_not_send():
    provider = LLMProvider(api_key="test")
    response = LLMResponse(
        content=json.dumps(
            dict.fromkeys(SUMMARY_FIELDS, "") | {"source_message_ids": ["one"]}
        ),
        output_usage=parse_output_usage({"completion_tokens": 3000}),
    )
    provider.chat = AsyncMock(return_value=response)
    provider.input_budget = lambda **kwargs: SimpleNamespace(
        estimate=SimpleNamespace(tokens=1 if len(kwargs["messages"]) == 1 else 100),
        input_limit_tokens=50,
    )
    diagnostics = []
    try:
        with pytest.raises(ValueError, match="输入预算"):
            await SummaryRequest(provider, "model", 8000, 2000).rewrite(
                [{"role": "user", "content": "state"}], {"one"}, diagnostics
            )
        assert provider.chat.await_count == 1
        assert [item.outcome for item in diagnostics] == ["oversized", "input_overflow"]
        assert [item.rewrite for item in diagnostics] == [0, 1]
    finally:
        await provider.aclose()
