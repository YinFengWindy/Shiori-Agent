"""Only validated model-authored messages may leave a natural-chat turn."""

import asyncio
import json
from unittest.mock import AsyncMock

import pytest

from agent.core.passive_turn.natural_reply import (
    InvalidNaturalReply,
    NaturalReplyProtocol,
)
from agent.provider import LLMProvider, LLMResponse, ToolCall
from agent.turns.reply_sequence import parse_reply_sequence
from agent.turns.reply_interruption import (
    ReplyInterruption,
    ReplyPlanInvalidated,
    reply_interruption_scope,
)


def completed(messages):
    return LLMResponse(
        content="",
        tool_calls=[ToolCall("reply", "finish_reply", {"messages": messages})],
    )


async def test_preserves_independent_messages_with_quotes_fences_and_literal_protocol():
    contents = ['她说："等我"\n<message-break/>', '```python\nprint("hi")', "下一条"]
    raw = json.dumps({"messages": contents}, ensure_ascii=False)
    response = completed(contents)
    response.tool_calls[0].raw_arguments = raw
    protocol = NaturalReplyProtocol()
    provider = AsyncMock()

    result = await protocol.complete(
        response, messages=[], provider=provider, model="m", max_tokens=4000
    )

    assert protocol.reply is not None
    assert protocol.reply.raw_text == raw
    assert parse_reply_sequence(
        protocol.reply.decorated_input, protocol.reply.policy
    ).messages == tuple(contents)
    assert result.response.content == "\n\n".join(contents)
    assert result.response.tool_calls == []
    provider.chat.assert_not_called()


@pytest.mark.parametrize(
    "response",
    [
        LLMResponse(content="第一句\n\n第二句", thinking="原本的思考"),
        completed([]),
        completed([""]),
        completed([" "]),
        completed(["第一句", 2]),
        completed("不是数组"),
        LLMResponse(
            content="",
            tool_calls=[ToolCall("reply", "finish_reply", {"messages": ["未完成"]})],
            finish_reason="length",
        ),
        LLMResponse(
            content="",
            tool_calls=[
                ToolCall("reply", "finish_reply", {}, '{"messages":', "invalid JSON")
            ],
        ),
    ],
)
async def test_invalid_completion_gets_one_reply_only_correction(response):
    protocol = NaturalReplyProtocol()
    provider = AsyncMock()
    provider.chat.return_value = completed(["第一句", "第二句"])
    original_messages = [{"role": "user", "content": "聊天"}]

    result = await protocol.complete(
        response,
        messages=original_messages,
        provider=provider,
        model="m",
        max_tokens=4000,
    )

    assert protocol.corrected
    assert protocol.reply is not None
    assert protocol.reply.sequence.messages == ("第一句", "第二句")
    assert result.calls[0] is response
    assert result.response.thinking == response.thinking
    assert original_messages == [{"role": "user", "content": "聊天"}]
    request = provider.chat.call_args.kwargs
    assert [tool["function"]["name"] for tool in request["tools"]] == ["finish_reply"]
    assert request["tool_choice"]["function"]["name"] == "finish_reply"
    assert request["call_purpose"] == "auxiliary"
    assert request["max_tokens"] == 4000
    assert provider.chat.await_count == 1


@pytest.mark.parametrize(
    "correction",
    [
        LLMResponse(content="依然只有普通正文"),
        completed([""]),
        LLMResponse(content="", tool_calls=[ToolCall("wrong", "counter", {})]),
    ],
)
async def test_failed_correction_never_silently_accepts_plain_text(correction):
    provider = AsyncMock()
    provider.chat.return_value = correction
    protocol = NaturalReplyProtocol()
    with pytest.raises(InvalidNaturalReply):
        await protocol.complete(
            LLMResponse(content="第一句\n\n第二句"),
            messages=[],
            provider=provider,
            model="m",
            max_tokens=4000,
        )
    assert provider.chat.await_count == 1
    assert protocol.reply is None


async def test_cancellation_during_correction_does_not_retry_or_publish():
    provider = AsyncMock()
    provider.chat.side_effect = asyncio.CancelledError
    protocol = NaturalReplyProtocol()
    with pytest.raises(asyncio.CancelledError):
        await protocol.complete(
            LLMResponse(content="正文"),
            messages=[],
            provider=provider,
            model="m",
            max_tokens=4000,
        )
    assert provider.chat.await_count == 1
    assert protocol.reply is None


@pytest.mark.parametrize("already_invalidated", [False, True])
async def test_superseded_reply_cannot_start_or_finish_a_format_correction(
    already_invalidated,
):
    interruption = ReplyInterruption(invalidated=already_invalidated)
    provider = AsyncMock()

    async def correct(**kwargs):
        interruption.invalidate()
        return completed(["已经过时的回复"])

    provider.chat.side_effect = correct
    protocol = NaturalReplyProtocol()
    with reply_interruption_scope(interruption), pytest.raises(ReplyPlanInvalidated):
        await protocol.complete(
            LLMResponse(content="第一句\n\n第二句"),
            messages=[],
            provider=provider,
            model="m",
            max_tokens=100,
        )
    assert protocol.reply is None
    assert provider.chat.await_count == (0 if already_invalidated else 1)


@pytest.mark.parametrize(
    "endpoint,strict",
    [
        ("https://api.deepseek.com/beta", True),
        ("https://api.deepseek.com/v1", False),
        ("https://api.openai.com/v1", True),
        ("https://example.test/v1", False),
    ],
)
async def test_correction_uses_strict_schema_only_on_supported_endpoint(
    endpoint, strict
):
    provider = LLMProvider(api_key="test", base_url=endpoint)
    provider.chat = AsyncMock(return_value=completed(["回复"]))
    try:
        await NaturalReplyProtocol().complete(
            LLMResponse(content="回复"),
            messages=[],
            provider=provider,
            model="m",
            max_tokens=100,
        )
        function = provider.chat.call_args.kwargs["tools"][0]["function"]
        assert function.get("strict", False) is strict
        assert function["parameters"]["required"] == ["messages"]
    finally:
        await provider.aclose()
