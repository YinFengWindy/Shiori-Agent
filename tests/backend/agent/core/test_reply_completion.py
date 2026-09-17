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


async def test_fetch_role_mood_labels_truncation_distinctly_from_malformed_json(
    caplog,
):
    """Issue #304: a `max_tokens` cutoff (finish_reason="length") with an
    empty `content` used to fall straight into `json.loads("")`, producing
    the exact same `Expecting value` error as a genuinely malformed reply -
    the misdiagnosis that slowed the 2026-09-17 qqbot investigation. The
    truncation case must now be reported as truncation, not as a JSON
    parse failure, and must never reach json.loads at all.
    """
    provider = AsyncMock()
    provider.chat.return_value = LLMResponse(content="", finish_reason="length")
    with caplog.at_level("WARNING"):
        reply = await fetch_role_mood(
            provider=provider,
            model="deepseek-v4-flash",
            max_tokens=300,
            messages=[{"role": "user", "content": "你好"}],
            content="正文",
            moods=("平静",),
        )
    assert reply is None
    messages = [record.getMessage() for record in caplog.records]
    assert any("截断" in message for message in messages)
    assert any("finish_reason=length" in message for message in messages)
    assert any("deepseek-v4-flash" in message for message in messages)
    # Must not also emit a generic "获取失败" / json.loads-style message for
    # the same call - truncation and parse failure are reported once, as
    # one thing, not conflated.
    assert not any("获取失败" in message for message in messages)


async def test_fetch_role_mood_logs_raw_output_on_complete_but_malformed_json(
    caplog,
):
    """A complete (finish_reason="stop") but non-JSON reply is a genuine
    format failure, distinct from truncation, and must log the raw model
    output plus model/finish_reason context so the failed round is still
    diagnosable afterward.
    """
    provider = AsyncMock()
    provider.chat.return_value = LLMResponse(
        content="不是 JSON 的正文", finish_reason="stop"
    )
    with caplog.at_level("WARNING"):
        reply = await fetch_role_mood(
            provider=provider,
            model="deepseek-v4-flash",
            max_tokens=300,
            messages=[],
            content="正文",
            moods=("平静",),
        )
    assert reply is None
    messages = [record.getMessage() for record in caplog.records]
    assert any("获取失败" in message for message in messages)
    assert any("finish_reason=stop" in message for message in messages)
    assert any("不是 JSON 的正文" in message for message in messages)
    assert not any("截断" in message for message in messages)


async def test_fetch_role_mood_raw_output_log_is_capped_and_redacts_secrets(caplog):
    """The raw output logged on failure must not flood logs or leak
    credential-shaped substrings the model might echo back."""
    leaked_key = "sk-" + "a" * 40
    long_payload = f"{leaked_key} " + "x" * 1000
    provider = AsyncMock()
    provider.chat.return_value = LLMResponse(content=long_payload, finish_reason="stop")
    with caplog.at_level("WARNING"):
        reply = await fetch_role_mood(
            provider=provider,
            model="m",
            max_tokens=300,
            messages=[],
            content="正文",
            moods=("平静",),
        )
    assert reply is None
    logged = "\n".join(record.getMessage() for record in caplog.records)
    assert leaked_key not in logged
    assert "REDACTED" in logged
    assert long_payload not in logged


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
