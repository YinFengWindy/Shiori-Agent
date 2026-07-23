from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from agent.provider import LLMProvider


def test_provider_disables_sdk_retries(monkeypatch: pytest.MonkeyPatch) -> None:
    created: dict[str, object] = {}

    class FakeAsyncOpenAI:
        def __init__(self, **kwargs: object) -> None:
            created.update(kwargs)

    monkeypatch.setattr("agent.provider.AsyncOpenAI", FakeAsyncOpenAI)

    LLMProvider(api_key="test-key", base_url="https://example.test/v1")

    assert created["max_retries"] == 0


@pytest.mark.asyncio
async def test_provider_retries_once_after_a_retryable_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    provider = LLMProvider(api_key="test-key", max_retries=1)
    completion = object()
    create = AsyncMock(side_effect=[TimeoutError("upstream unavailable"), completion])
    provider._client = SimpleNamespace(
        chat=SimpleNamespace(completions=SimpleNamespace(create=create))
    )
    sleep = AsyncMock()
    monkeypatch.setattr("agent.provider.asyncio.sleep", sleep)

    result = await provider._create_with_retry({"model": "test-model"})

    assert result is completion
    assert create.await_count == 2
    sleep.assert_awaited_once_with(1.0)
