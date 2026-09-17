"""Fetch a role's mood/thought after the fact, without ever failing the reply."""

import json
from unittest.mock import AsyncMock

from agent.core.reply_completion import fetch_role_mood
from agent.provider import LLMResponse


def mood_payload(mood="平静", thought="我终于放心了。"):
    return json.dumps({"mood": mood, "thought": thought}, ensure_ascii=False)


async def test_fetch_role_mood_reuses_prefix_and_appends_produced_content():
    provider = AsyncMock()
    provider.chat.return_value = LLMResponse(content=mood_payload())
    reply = await fetch_role_mood(
        provider=provider,
        model="m",
        max_tokens=200,
        messages=[{"role": "user", "content": "你好"}],
        content='她说："稍等"，（转身离开）。\n然后走了。',
        moods=("平静",),
    )
    assert reply is not None
    assert reply.content == '她说："稍等"，（转身离开）。\n然后走了。'
    assert reply.mood == "平静"
    assert reply.thought == "我终于放心了。"
    request = provider.chat.call_args.kwargs
    assert request["disable_thinking"] is True
    assert request["response_format"] == {"type": "json_object"}
    assert request["messages"][0] == {"role": "user", "content": "你好"}
    assert request["messages"][1] == {
        "role": "assistant",
        "content": '她说："稍等"，（转身离开）。\n然后走了。',
    }
    assert request["messages"][1]["content"] == reply.content


async def test_fetch_role_mood_returns_none_on_transport_failure():
    provider = AsyncMock()
    provider.chat.side_effect = TimeoutError("断流")
    reply = await fetch_role_mood(
        provider=provider,
        model="m",
        max_tokens=200,
        messages=[{"role": "user", "content": "你好"}],
        content="正文",
        moods=("平静",),
    )
    assert reply is None


async def test_fetch_role_mood_returns_none_on_malformed_json():
    provider = AsyncMock()
    provider.chat.return_value = LLMResponse(content="不是 JSON")
    reply = await fetch_role_mood(
        provider=provider,
        model="m",
        max_tokens=200,
        messages=[],
        content="正文",
        moods=("平静",),
    )
    assert reply is None


async def test_fetch_role_mood_returns_none_when_mood_outside_catalog():
    provider = AsyncMock()
    provider.chat.return_value = LLMResponse(content=mood_payload(mood="未知"))
    reply = await fetch_role_mood(
        provider=provider,
        model="m",
        max_tokens=200,
        messages=[],
        content="正文",
        moods=("平静",),
    )
    assert reply is None


async def test_fetch_role_mood_returns_none_when_thought_missing_first_person():
    provider = AsyncMock()
    provider.chat.return_value = LLMResponse(content=mood_payload(thought="她很开心。"))
    reply = await fetch_role_mood(
        provider=provider,
        model="m",
        max_tokens=200,
        messages=[],
        content="正文",
        moods=("平静",),
    )
    assert reply is None


async def test_fetch_role_mood_ignores_model_echoed_content_field():
    """The model must never be able to rewrite the already-delivered content
    through this follow-up call; our own `content` always wins."""
    provider = AsyncMock()
    provider.chat.return_value = LLMResponse(
        content=json.dumps(
            {"content": "改写正文", "mood": "平静", "thought": "我很开心。"},
            ensure_ascii=False,
        )
    )
    reply = await fetch_role_mood(
        provider=provider,
        model="m",
        max_tokens=200,
        messages=[],
        content="真正的正文",
        moods=("平静",),
    )
    assert reply is not None
    assert reply.content == "真正的正文"
