"""Retrieval hypotheses use a small auxiliary output budget."""

from unittest.mock import AsyncMock

from agent.provider import LLMResponse
from plugins.default_memory.backend.engine.lifecycle import DefaultMemoryEngine


async def test_retrieval_hypothesis_requests_auxiliary_reasoning(monkeypatch):
    provider = AsyncMock()
    provider.chat.return_value = LLMResponse(content="你喜欢拿铁")
    engine = DefaultMemoryEngine.__new__(DefaultMemoryEngine)
    monkeypatch.setattr(engine, "_light_provider", provider, raising=False)
    monkeypatch.setattr(engine, "_light_model", "retrieval-model", raising=False)

    result = await engine._gen_hypothesis("我喜欢喝什么？", "preference")

    assert result == "你喜欢拿铁"
    request = provider.chat.await_args.kwargs
    assert request["call_purpose"] == "auxiliary"
    assert request["max_tokens"] == 80
