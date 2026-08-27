from __future__ import annotations

from types import SimpleNamespace

import pytest

from agent.core.mood_resolver import resolve_role_mood


class _FakeProvider:
    def __init__(self, response_content: str) -> None:
        self._response_content = response_content

    async def chat(self, **kwargs):  # type: ignore[no-untyped-def]
        return SimpleNamespace(content=self._response_content)


@pytest.mark.asyncio
async def test_resolve_role_mood_returns_catalog_item_from_llm_json() -> None:
    provider = _FakeProvider('{"mood":"开心"}')

    resolved = await resolve_role_mood(
        provider,  # type: ignore[arg-type]
        model="test-model",
        max_tokens=256,
        reply_text="她轻轻笑了一下。",
        available_moods=["平静", "开心", "嫌弃"],
        default_mood="平静",
    )

    assert resolved == "开心"


@pytest.mark.asyncio
async def test_resolve_role_mood_falls_back_to_default_for_unknown_label() -> None:
    provider = _FakeProvider('{"mood":"快乐"}')

    resolved = await resolve_role_mood(
        provider,  # type: ignore[arg-type]
        model="test-model",
        max_tokens=256,
        reply_text="她轻轻笑了一下。",
        available_moods=["平静", "开心", "嫌弃"],
        default_mood="平静",
    )

    assert resolved == "平静"
