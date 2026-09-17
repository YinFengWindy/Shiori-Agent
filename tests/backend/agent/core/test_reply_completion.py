"""Correct malformed final output once without tools or duplicated speech."""

import asyncio
import json
from unittest.mock import AsyncMock

import pytest

from agent.core.reply_completion import complete_role_reply
from agent.core.reply_stream import RoleReplyStream
from agent.provider import LLMResponse, ContextLengthError, ContentSafetyError
from core.roles.reply_state import InvalidRoleReply


def payload(content="你好"):
    return json.dumps(
        {"content": content, "mood": "平静", "thought": "我终于放心了。"},
        ensure_ascii=False,
    )


async def run_completion(response, provider, *, stream=None, threshold=0):
    return await complete_role_reply(
        response,
        provider=provider,
        model="m",
        max_tokens=2000,
        messages=[{"role": "tool", "tool_call_id": "done", "content": "工具已完成"}],
        moods=("平静",),
        stream=stream or RoleReplyStream(None),
        input_token_threshold=threshold,
    )


async def test_reasoning_mood_does_not_replace_missing_formal_output():
    provider = AsyncMock()
    provider.chat.return_value = LLMResponse(content=payload())
    response, correction = await run_completion(
        LLMResponse(content="纯文本", thinking="mood 平静"), provider
    )
    assert response.content == correction.content
    assert json.loads(response.content)["mood"] == "平静"
    request = provider.chat.call_args.kwargs
    assert request["tools"] == []
    assert request["response_format"] == {"type": "json_object"}
    assert request["messages"][0]["tool_call_id"] == "done"
    assert "mood 平静" not in json.dumps(request["messages"], ensure_ascii=False)


async def test_second_invalid_reply_fails_without_fallback_or_third_call():
    provider = AsyncMock()
    provider.chat.return_value = LLMResponse(content="仍是纯文本")
    with pytest.raises(InvalidRoleReply):
        await run_completion(LLMResponse(content="纯文本"), provider)
    assert provider.chat.await_count == 1


@pytest.mark.parametrize("failure", [asyncio.CancelledError(), TimeoutError("断流")])
async def test_correction_cancellation_and_transport_failure_propagate(failure):
    provider = AsyncMock()
    provider.chat.side_effect = failure
    with pytest.raises(type(failure)):
        await run_completion(LLMResponse(content=""), provider)
    assert provider.chat.await_count == 1


async def test_correction_budget_stops_before_provider_request():
    provider = AsyncMock()
    with pytest.raises(InvalidRoleReply, match="预算"):
        await run_completion(LLMResponse(content=""), provider, threshold=1)
    provider.chat.assert_not_called()


@pytest.mark.parametrize(
    "error", [ContextLengthError("long"), ContentSafetyError("blocked")]
)
async def test_rejected_correction_cannot_trigger_outer_context_retry(error):
    provider = AsyncMock()
    provider.chat.side_effect = error
    with pytest.raises(InvalidRoleReply, match="被模型拒绝"):
        await run_completion(LLMResponse(content=""), provider)
    assert provider.chat.await_count == 1


async def test_corrected_reply_never_repeats_already_spoken_content():
    emitted = []

    async def sink(delta):
        emitted.append(delta.get("content_delta", ""))

    stream = RoleReplyStream(sink)
    await stream.push('{"content":"你好"}')

    async def chat(**kwargs):
        await kwargs["on_content_delta"]({"content_delta": payload()})
        return LLMResponse(content=payload())

    provider = AsyncMock()
    provider.chat.side_effect = chat
    await run_completion(
        LLMResponse(content='{"content":"你好"}'), provider, stream=stream
    )
    assert "".join(emitted) == "你好"
    assert "你好" in provider.chat.call_args.kwargs["messages"][-1]["content"]


async def test_correction_preserves_first_attempt_thinking_when_correction_has_none():
    """The main response must keep the first attempt's already-streamed thinking
    even when the correction round produces none, so it is not silently dropped
    from persistence (issue #300)."""
    provider = AsyncMock()
    provider.chat.return_value = LLMResponse(content=payload())
    response, correction = await run_completion(
        LLMResponse(content="纯文本", thinking="第一次的思考"), provider
    )
    assert response.thinking == "第一次的思考"
    assert correction.thinking is None


async def test_correction_concatenates_thinking_from_both_attempts_in_order():
    """When both the first attempt and the correction stream thinking to the
    user, the main response must expose both, first-attempt text first."""

    async def chat(**kwargs):
        return LLMResponse(content=payload(), thinking="纠正阶段的思考")

    provider = AsyncMock()
    provider.chat.side_effect = chat
    response, correction = await run_completion(
        LLMResponse(content="纯文本", thinking="第一次的思考"), provider
    )
    assert response.thinking == "第一次的思考纠正阶段的思考"
    assert correction.thinking == "纠正阶段的思考"
