from __future__ import annotations

import asyncio
import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

import agent.provider as provider_module
from agent.provider import (
    ContentSafetyError,
    ContextLengthError,
    LLMProvider,
    _normalize_openai_base_url,
    is_truncated_finish_reason,
)
from agent.tool_runtime import append_assistant_tool_calls


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


class _Response:
    def __init__(
        self,
        content: str = "ok",
        tool_calls: list | None = None,
        reasoning_content: str | None = None,
        usage: object | None = None,
        finish_reason: str | None = "stop",
    ) -> None:
        message = SimpleNamespace(content=content, tool_calls=tool_calls or [])
        if reasoning_content is not None:
            message.reasoning_content = reasoning_content
        self.choices = [SimpleNamespace(message=message, finish_reason=finish_reason)]
        self.usage = usage


class _ToolCall:
    def __init__(self, id: str, name: str, arguments: dict) -> None:
        self.id = id
        self.function = SimpleNamespace(
            name=name, arguments=json.dumps(arguments, ensure_ascii=False)
        )


class _RawToolCall:
    """A tool call whose `arguments` is an arbitrary (possibly invalid or
    truncated) raw string, for driving json.loads failure paths."""

    def __init__(self, id: str, name: str, raw_arguments: str) -> None:
        self.id = id
        self.function = SimpleNamespace(name=name, arguments=raw_arguments)


class _FakeClient:
    def __init__(self, responses: list[object]) -> None:
        self._responses = responses
        self.calls: list[dict] = []
        self.chat = SimpleNamespace(
            completions=SimpleNamespace(create=self.create),
        )

    async def create(self, **kwargs):
        self.calls.append(kwargs)
        response = self._responses.pop(0)
        if isinstance(response, Exception):
            raise response
        return response


class _FakeStream:
    def __init__(self, chunks: list[object], delay_s: float = 0.0) -> None:
        self._chunks = list(chunks)
        self._delay_s = delay_s

    def __aiter__(self):
        return self

    async def __anext__(self):
        if not self._chunks:
            raise StopAsyncIteration
        if self._delay_s:
            await asyncio.sleep(self._delay_s)
        return self._chunks.pop(0)


async def _collect_delta(bucket: list, chunk) -> None:
    bucket.append(chunk)


@pytest.mark.asyncio
async def test_role_json_mode_is_explicit_and_background_calls_stay_unconstrained(
    monkeypatch,
):
    fake = _FakeClient(
        [
            _Response(
                content='{"content":"你好","mood":"平静","thought":"我放心了。"}'
            ),
            _Response(content="background"),
        ]
    )
    monkeypatch.setattr("agent.provider.AsyncOpenAI", lambda **_: fake)
    provider = LLMProvider(
        api_key="k", provider_name="deepseek", base_url="https://api.deepseek.com"
    )
    await provider.chat(
        messages=[{"role": "user", "content": "输出 JSON"}],
        tools=[],
        model="deepseek-chat",
        max_tokens=1000,
        response_format={"type": "json_object"},
    )
    await provider.chat(
        messages=[{"role": "user", "content": "summarize"}],
        tools=[],
        model="deepseek-chat",
        max_tokens=1000,
    )
    assert fake.calls[0]["response_format"] == {"type": "json_object"}
    assert "response_format" not in fake.calls[1]


@pytest.mark.asyncio
async def test_provider_chat_and_retry_paths(monkeypatch: pytest.MonkeyPatch):
    fake = _FakeClient(
        [
            RuntimeError("timeout"),
            _Response(
                content="done",
                tool_calls=[_ToolCall("1", "search", {"q": "x"})],
            ),
        ]
    )
    monkeypatch.setattr("agent.provider.AsyncOpenAI", lambda **_: fake)
    slept = []

    async def _sleep(sec: float) -> None:
        slept.append(sec)

    monkeypatch.setattr("agent.provider.asyncio.sleep", _sleep)
    provider = LLMProvider(
        api_key="k",
        base_url="https://example.com",
        extra_body={"x": 1},
        request_timeout_s=3,
        max_retries=1,
    )
    result = await provider.chat(
        messages=[{"role": "user", "content": "hi"}],
        tools=[{"type": "function"}],
        model="m",
        max_tokens=10,
    )
    assert result.content == "done"
    assert result.tool_calls[0].arguments == {"q": "x"}
    assert fake.calls[-1]["messages"][0]["role"] == "user"
    assert fake.calls[-1]["extra_body"] == {"x": 1}
    assert slept == [1.0]

    fake = _FakeClient(
        [
            _Response(
                content="cache-ok",
                usage=SimpleNamespace(
                    prompt_cache_hit_tokens=12,
                    prompt_cache_miss_tokens=28,
                    total_tokens=64,
                ),
            )
        ]
    )
    monkeypatch.setattr("agent.provider.AsyncOpenAI", lambda **_: fake)
    result = await LLMProvider(api_key="k", provider_name="deepseek").chat(
        [], [], "deepseek-v4-flash", 1
    )
    assert result.cache_prompt_tokens == 40
    assert result.cache_hit_tokens == 12
    assert result.total_tokens == 64

    fake = _FakeClient(
        [
            _Response(
                content="mimo-cache-ok",
                usage=SimpleNamespace(
                    prompt_tokens=100,
                    completion_tokens=24,
                    prompt_tokens_details=SimpleNamespace(cached_tokens=76),
                ),
            )
        ]
    )
    monkeypatch.setattr("agent.provider.AsyncOpenAI", lambda **_: fake)
    result = await LLMProvider(api_key="k").chat([], [], "mimo-v2.5", 1)
    assert result.cache_prompt_tokens == 100
    assert result.cache_hit_tokens == 76
    assert result.total_tokens == 124

    fake = _FakeClient(
        [
            RuntimeError("Error code: 429"),
            _Response(content="retry-ok"),
        ]
    )
    monkeypatch.setattr("agent.provider.AsyncOpenAI", lambda **_: fake)
    slept = []
    monkeypatch.setattr("agent.provider.asyncio.sleep", _sleep)
    result = await LLMProvider(api_key="k", max_retries=1).chat([], [], "m", 1)
    assert result.content == "retry-ok"
    assert slept == [1.0]

    fake = _FakeClient([RuntimeError("content_policy_violation")])
    monkeypatch.setattr("agent.provider.AsyncOpenAI", lambda **_: fake)
    with pytest.raises(ContentSafetyError):
        await LLMProvider(api_key="k").chat([], [], "m", 1)

    fake = _FakeClient([RuntimeError("maximum context length exceeded")])
    monkeypatch.setattr("agent.provider.AsyncOpenAI", lambda **_: fake)
    with pytest.raises(ContextLengthError):
        await LLMProvider(api_key="k").chat([], [], "m", 1)

    fake = _FakeClient([RuntimeError("invalid_parameter_error")])
    monkeypatch.setattr("agent.provider.AsyncOpenAI", lambda **_: fake)
    with pytest.raises(RuntimeError):
        await LLMProvider(api_key="k", max_retries=0).chat([], [], "m", 1)

    fake = _FakeClient([RuntimeError("bad request")])
    monkeypatch.setattr("agent.provider.AsyncOpenAI", lambda **_: fake)
    with pytest.raises(RuntimeError):
        await LLMProvider(api_key="k", max_retries=0).chat([], [], "m", 1)


def test_normalize_openai_base_url_trims_endpoint_suffix():
    assert (
        _normalize_openai_base_url("https://pro.nasdw.top:888/v1/chat/completions")
        == "https://pro.nasdw.top:888/v1"
    )
    assert (
        _normalize_openai_base_url("https://example.com/v1/responses")
        == "https://example.com/v1"
    )
    assert _normalize_openai_base_url("https://example.com") == "https://example.com"


@pytest.mark.asyncio
async def test_provider_payload_snapshot_switch_default_off_and_opt_in(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
):
    snapshot_dir = tmp_path / "payloads"
    last_payload = tmp_path / "last.json"
    monkeypatch.setattr(provider_module, "_PAYLOAD_SNAPSHOT_DIR", snapshot_dir)
    monkeypatch.setattr(provider_module, "_LAST_PAYLOAD_PATH", last_payload)

    stream = _FakeStream([SimpleNamespace(choices=[])])
    fake = _FakeClient(
        [
            _Response(content="off"),
            _Response(content="ok"),
            stream,
            _Response(content="private"),
        ]
    )
    monkeypatch.setattr("agent.provider.AsyncOpenAI", lambda **_: fake)

    provider = LLMProvider(api_key="k")
    await provider.chat(
        messages=[{"role": "user", "content": "off"}],
        tools=[],
        model="m",
        max_tokens=10,
    )

    assert not snapshot_dir.exists()
    assert not last_payload.exists()

    monkeypatch.setattr(provider_module, "_LLM_PAYLOAD_SNAPSHOT_ENABLED", True)
    provider_enabled = LLMProvider(api_key="k")
    await provider_enabled.chat(
        messages=[{"role": "user", "content": "hi"}],
        tools=[],
        model="m",
        max_tokens=10,
    )
    await provider_enabled.chat(
        messages=[{"role": "user", "content": "stream"}],
        tools=[],
        model="m",
        max_tokens=10,
        on_content_delta=lambda chunk: _collect_delta([], chunk),
    )
    await provider_enabled.chat(
        messages=[{"role": "user", "content": "private image"}],
        tools=[],
        model="m",
        max_tokens=10,
        payload_snapshot_enabled=False,
    )

    files = sorted(snapshot_dir.glob("*.json"))
    assert len(files) == 2
    first_payload = json.loads(files[0].read_text(encoding="utf-8"))
    second_payload = json.loads(files[1].read_text(encoding="utf-8"))
    assert first_payload["messages"][0]["content"] == "hi"
    assert second_payload["messages"][0]["content"] == "stream"
    assert second_payload["stream"] is True


@pytest.mark.asyncio
async def test_provider_payload_snapshot_can_enable_per_instance(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
):
    snapshot_dir = tmp_path / "payloads"
    last_payload = tmp_path / "last.json"
    monkeypatch.setattr(provider_module, "_PAYLOAD_SNAPSHOT_DIR", snapshot_dir)
    monkeypatch.setattr(provider_module, "_LAST_PAYLOAD_PATH", last_payload)
    monkeypatch.setattr(provider_module, "_LLM_PAYLOAD_SNAPSHOT_ENABLED", False)

    fake = _FakeClient([_Response(content="ok")])
    monkeypatch.setattr("agent.provider.AsyncOpenAI", lambda **_: fake)

    provider = LLMProvider(api_key="k", payload_snapshot_enabled=True)
    await provider.chat(
        messages=[{"role": "user", "content": "dev"}],
        tools=[],
        model="m",
        max_tokens=10,
    )

    files = sorted(snapshot_dir.glob("*.json"))
    assert len(files) == 1
    payload = json.loads(files[0].read_text(encoding="utf-8"))
    assert payload["messages"][0]["content"] == "dev"


@pytest.mark.asyncio
async def test_provider_chat_stream_parses_content_reasoning_and_tool_calls(
    monkeypatch: pytest.MonkeyPatch,
):
    stream = _FakeStream(
        [
            SimpleNamespace(
                choices=[
                    SimpleNamespace(
                        delta=SimpleNamespace(
                            content="你", reasoning_content="想", tool_calls=[]
                        )
                    )
                ]
            ),
            SimpleNamespace(
                choices=[
                    SimpleNamespace(
                        delta=SimpleNamespace(
                            content="好", reasoning_content="法", tool_calls=[]
                        )
                    )
                ]
            ),
            SimpleNamespace(
                choices=[],
                usage=SimpleNamespace(
                    prompt_cache_hit_tokens=16,
                    prompt_cache_miss_tokens=48,
                ),
            ),
        ]
    )
    fake = _FakeClient([stream])
    monkeypatch.setattr("agent.provider.AsyncOpenAI", lambda **_: fake)
    deltas: list[dict[str, str]] = []
    provider = LLMProvider(api_key="k")
    result = await provider.chat(
        messages=[{"role": "user", "content": "hi"}],
        tools=[],
        model="m",
        max_tokens=10,
        on_content_delta=lambda chunk: _collect_delta(deltas, chunk),
    )
    assert result.content == "你好"
    assert result.thinking == "想法"
    content_deltas = [d["content_delta"] for d in deltas if "content_delta" in d]
    thinking_deltas = [d["thinking_delta"] for d in deltas if "thinking_delta" in d]
    assert content_deltas == ["你", "好"]
    assert thinking_deltas == ["想", "法"]
    assert fake.calls[0]["stream"] is True
    assert result.cache_prompt_tokens == 64
    assert result.cache_hit_tokens == 16


@pytest.mark.asyncio
async def test_provider_chat_stream_extracts_openai_cached_tokens(
    monkeypatch: pytest.MonkeyPatch,
):
    stream = _FakeStream(
        [
            SimpleNamespace(
                choices=[
                    SimpleNamespace(delta=SimpleNamespace(content="好", tool_calls=[]))
                ]
            ),
            SimpleNamespace(
                choices=[],
                usage=SimpleNamespace(
                    prompt_tokens=100,
                    prompt_tokens_details={"cached_tokens": 80},
                ),
            ),
        ]
    )
    fake = _FakeClient([stream])
    monkeypatch.setattr("agent.provider.AsyncOpenAI", lambda **_: fake)
    provider = LLMProvider(api_key="k")

    result = await provider.chat(
        messages=[],
        tools=[],
        model="mimo-v2.5",
        max_tokens=10,
        on_content_delta=lambda chunk: _collect_delta([], chunk),
    )

    assert result.content == "好"
    assert result.cache_prompt_tokens == 100
    assert result.cache_hit_tokens == 80


@pytest.mark.asyncio
async def test_provider_chat_stream_times_out_when_idle(
    monkeypatch: pytest.MonkeyPatch,
):
    stream = _FakeStream(
        [
            SimpleNamespace(
                choices=[
                    SimpleNamespace(delta=SimpleNamespace(content="慢", tool_calls=[]))
                ]
            )
        ],
        delay_s=0.05,
    )
    fake = _FakeClient([stream])
    monkeypatch.setattr("agent.provider.AsyncOpenAI", lambda **_: fake)

    provider = LLMProvider(
        api_key="k",
        stream_idle_timeout_s=0.01,
        max_retries=0,
    )
    with pytest.raises(asyncio.TimeoutError):
        await provider.chat(
            messages=[{"role": "user", "content": "hi"}],
            tools=[],
            model="m",
            max_tokens=10,
            on_content_delta=lambda chunk: _collect_delta([], chunk),
        )


@pytest.mark.asyncio
async def test_deepseek_strategy_maps_thinking_config(monkeypatch: pytest.MonkeyPatch):
    fake = _FakeClient([_Response(content="ok")])
    monkeypatch.setattr("agent.provider.AsyncOpenAI", lambda **_: fake)
    provider = LLMProvider(
        api_key="k",
        provider_name="deepseek",
        extra_body={"enable_thinking": True, "reasoning_effort": "xhigh"},
    )

    await provider.chat(
        messages=[{"role": "user", "content": "hi"}],
        tools=[],
        model="deepseek-v4-pro",
        max_tokens=10,
    )

    assert fake.calls[-1]["extra_body"] == {"thinking": {"type": "enabled"}}
    assert fake.calls[-1]["reasoning_effort"] == "max"


@pytest.mark.asyncio
async def test_deepseek_strategy_disables_thinking(monkeypatch: pytest.MonkeyPatch):
    fake = _FakeClient([_Response(content="ok")])
    monkeypatch.setattr("agent.provider.AsyncOpenAI", lambda **_: fake)
    provider = LLMProvider(
        api_key="k",
        provider_name="deepseek",
        extra_body={
            "enable_thinking": True,
            "thinking": {"type": "enabled"},
            "reasoning_effort": "high",
        },
    )

    await provider.chat(
        messages=[{"role": "user", "content": "hi"}],
        tools=[],
        model="deepseek-v4-pro",
        max_tokens=10,
        disable_thinking=True,
    )

    assert fake.calls[-1]["extra_body"] == {"thinking": {"type": "disabled"}}
    assert "reasoning_effort" not in fake.calls[-1]


@pytest.mark.parametrize("streaming", [False, True])
@pytest.mark.parametrize("max_tokens", [128, 8192])
@pytest.mark.parametrize(
    "provider_name,expected_extra",
    [
        ("deepseek", {"thinking": {"type": "disabled"}, "temperature": 0.2}),
        ("dashscope", {"enable_thinking": False, "temperature": 0.2}),
        ("generic", {"temperature": 0.2}),
    ],
)
async def test_auxiliary_call_overrides_reasoning_without_mutating_config(
    monkeypatch, streaming, max_tokens, provider_name, expected_extra
):
    fake = _FakeClient([_FakeStream([]) if streaming else _Response(content="ok")])
    monkeypatch.setattr("agent.provider.AsyncOpenAI", lambda **_: fake)
    defaults = {"thinking": {"type": "enabled"}, "reasoning_effort": "high"}
    overrides = {"enable_thinking": True, "temperature": 0.2}
    provider = LLMProvider(
        api_key="k", provider_name=provider_name, extra_body=defaults
    )

    await provider.chat(
        messages=[{"role": "user", "content": "summarize"}],
        tools=[],
        model="model",
        max_tokens=max_tokens,
        extra_body=overrides,
        call_purpose="auxiliary",
        auxiliary_max_tokens=512,
        on_content_delta=AsyncMock() if streaming else None,
    )

    request = fake.calls[0]
    assert request["extra_body"] == expected_extra
    assert "reasoning_effort" not in request
    assert "call_purpose" not in request
    assert "auxiliary_max_tokens" not in request
    assert request["max_tokens"] == (
        max_tokens if provider_name == "generic" else min(max_tokens, 512)
    )
    assert request.get("stream", False) is streaming
    assert defaults == {"thinking": {"type": "enabled"}, "reasoning_effort": "high"}
    assert overrides == {"enable_thinking": True, "temperature": 0.2}


@pytest.mark.asyncio
async def test_token_plan_strategy_disables_thinking(monkeypatch: pytest.MonkeyPatch):
    fake = _FakeClient([_Response(content="ok")])
    monkeypatch.setattr("agent.provider.AsyncOpenAI", lambda **_: fake)
    provider = LLMProvider(
        api_key="k",
        base_url="https://token-plan-cn.xiaomimimo.com/v1",
        force_disable_thinking=True,
    )

    await provider.chat(
        messages=[{"role": "user", "content": "hi"}],
        tools=[],
        model="mimo-v2.5",
        max_tokens=10,
    )

    assert fake.calls[-1]["extra_body"] == {"enable_thinking": False}


@pytest.mark.asyncio
async def test_deepseek_strategy_keeps_image_url_blocks(
    monkeypatch: pytest.MonkeyPatch,
):
    fake = _FakeClient([_Response(content="ok")])
    monkeypatch.setattr("agent.provider.AsyncOpenAI", lambda **_: fake)
    provider = LLMProvider(api_key="k", provider_name="deepseek")

    await provider.chat(
        messages=[
            {
                "role": "user",
                "content": [
                    {
                        "type": "image_url",
                        "image_url": {"url": "data:image/png;base64,AAAA"},
                    },
                    {"type": "text", "text": "看看这张图"},
                ],
            }
        ],
        tools=[],
        model="deepseek-v4-pro",
        max_tokens=10,
    )

    # DeepSeek 已支持多模态输入，图片块必须原样透传而不是被降级成文本。
    assert fake.calls[-1]["messages"][0]["content"] == [
        {"type": "image_url", "image_url": {"url": "data:image/png;base64,AAAA"}},
        {"type": "text", "text": "看看这张图"},
    ]


@pytest.mark.asyncio
async def test_deepseek_tool_call_round_trips_reasoning_content(
    monkeypatch: pytest.MonkeyPatch,
):
    fake = _FakeClient(
        [
            _Response(
                content="",
                tool_calls=[_ToolCall("1", "search", {"q": "x"})],
                reasoning_content="先查资料",
            )
        ]
    )
    monkeypatch.setattr("agent.provider.AsyncOpenAI", lambda **_: fake)
    provider = LLMProvider(api_key="k", provider_name="deepseek")

    result = await provider.chat(
        messages=[{"role": "user", "content": "hi"}],
        tools=[{"type": "function"}],
        model="deepseek-v4-pro",
        max_tokens=10,
    )

    messages: list[dict] = []
    append_assistant_tool_calls(
        messages,
        content=result.content,
        tool_calls=result.tool_calls,
        provider_fields=result.provider_fields,
    )

    assert result.thinking == "先查资料"
    assert messages[0]["reasoning_content"] == "先查资料"


@pytest.mark.asyncio
async def test_deepseek_thinking_request_patches_dirty_history(
    monkeypatch: pytest.MonkeyPatch,
):
    fake = _FakeClient([_Response(content="ok")])
    monkeypatch.setattr("agent.provider.AsyncOpenAI", lambda **_: fake)
    provider = LLMProvider(
        api_key="k",
        provider_name="deepseek",
        extra_body={"enable_thinking": True},
    )

    await provider.chat(
        messages=[
            {"role": "user", "content": "hi"},
            {"role": "assistant", "content": "old reply"},
            {"role": "user", "content": "again"},
        ],
        tools=[],
        model="deepseek-v4-pro",
        max_tokens=10,
    )

    assert fake.calls[-1]["messages"][1]["reasoning_content"] == ""


# --- issue #304: finish_reason visibility + parse-failure raw output logging ---


@pytest.mark.asyncio
async def test_non_streaming_chat_reports_truncation_finish_reason(
    monkeypatch: pytest.MonkeyPatch,
):
    """A `max_tokens` cutoff on the non-streaming path must surface on the
    response so callers can tell it apart from a genuinely empty/malformed
    reply instead of both looking identical."""
    fake = _FakeClient([_Response(content="", finish_reason="length")])
    monkeypatch.setattr("agent.provider.AsyncOpenAI", lambda **_: fake)
    provider = LLMProvider(api_key="k")

    result = await provider.chat(messages=[], tools=[], model="m", max_tokens=10)

    assert result.finish_reason == "length"
    assert is_truncated_finish_reason(result.finish_reason) is True


@pytest.mark.asyncio
async def test_non_streaming_chat_reports_natural_stop_finish_reason(
    monkeypatch: pytest.MonkeyPatch,
):
    fake = _FakeClient([_Response(content="ok", finish_reason="stop")])
    monkeypatch.setattr("agent.provider.AsyncOpenAI", lambda **_: fake)
    provider = LLMProvider(api_key="k")

    result = await provider.chat(messages=[], tools=[], model="m", max_tokens=10)

    assert result.finish_reason == "stop"
    assert is_truncated_finish_reason(result.finish_reason) is False


@pytest.mark.asyncio
async def test_streaming_chat_reports_truncation_finish_reason_from_fake_stream(
    monkeypatch: pytest.MonkeyPatch,
):
    """Same signal, streaming path: a fake stream whose terminal chunk
    carries finish_reason="length" on an otherwise-empty delta (the real
    shape most OpenAI-compatible APIs use) must still be picked up - the
    delta-is-None chunk cannot be skipped before finish_reason is read."""
    stream = _FakeStream(
        [
            SimpleNamespace(
                choices=[SimpleNamespace(delta=SimpleNamespace(content=""))]
            ),
            SimpleNamespace(
                choices=[SimpleNamespace(delta=None, finish_reason="length")]
            ),
        ]
    )
    fake = _FakeClient([stream])
    monkeypatch.setattr("agent.provider.AsyncOpenAI", lambda **_: fake)
    provider = LLMProvider(api_key="k")

    result = await provider.chat(
        messages=[{"role": "user", "content": "hi"}],
        tools=[],
        model="m",
        max_tokens=10,
        on_content_delta=lambda chunk: _collect_delta([], chunk),
    )

    assert result.content is None
    assert result.finish_reason == "length"
    assert is_truncated_finish_reason(result.finish_reason) is True


@pytest.mark.asyncio
async def test_streaming_chat_reports_natural_stop_finish_reason_from_fake_stream(
    monkeypatch: pytest.MonkeyPatch,
):
    stream = _FakeStream(
        [
            SimpleNamespace(
                choices=[SimpleNamespace(delta=SimpleNamespace(content="完整回复"))]
            ),
            SimpleNamespace(
                choices=[SimpleNamespace(delta=None, finish_reason="stop")]
            ),
        ]
    )
    fake = _FakeClient([stream])
    monkeypatch.setattr("agent.provider.AsyncOpenAI", lambda **_: fake)
    provider = LLMProvider(api_key="k")

    result = await provider.chat(
        messages=[{"role": "user", "content": "hi"}],
        tools=[],
        model="m",
        max_tokens=10,
        on_content_delta=lambda chunk: _collect_delta([], chunk),
    )

    assert result.content == "完整回复"
    assert result.finish_reason == "stop"
    assert is_truncated_finish_reason(result.finish_reason) is False


@pytest.mark.asyncio
async def test_non_streaming_tool_call_parse_failure_logs_context_then_raises(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
):
    """A complete-but-malformed tool call payload (finish_reason="stop")
    must log model/finish_reason/raw arguments before re-raising - the
    existing raise-on-failure behaviour for tool call parsing is
    unchanged, only now it leaves a diagnosable trail."""
    fake = _FakeClient(
        [
            _Response(
                content=None,
                tool_calls=[_RawToolCall("1", "search", "{not valid json")],
                finish_reason="stop",
            )
        ]
    )
    monkeypatch.setattr("agent.provider.AsyncOpenAI", lambda **_: fake)
    provider = LLMProvider(api_key="k")

    with caplog.at_level("WARNING"):
        with pytest.raises(json.JSONDecodeError):
            await provider.chat(
                messages=[], tools=[{"type": "function"}], model="m", max_tokens=10
            )

    messages = [record.getMessage() for record in caplog.records]
    assert any("finish_reason=stop" in message for message in messages)
    assert any("model=m" in message for message in messages)
    assert any("{not valid json" in message for message in messages)


@pytest.mark.asyncio
async def test_streaming_tool_call_parse_failure_logs_truncation_context(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
):
    """Same failure, streaming path: arguments cut off mid-JSON by a
    max_tokens ceiling (finish_reason="length") must log that distinction
    too before re-raising."""
    stream = _FakeStream(
        [
            SimpleNamespace(
                choices=[
                    SimpleNamespace(
                        delta=SimpleNamespace(
                            content=None,
                            tool_calls=[
                                SimpleNamespace(
                                    index=0,
                                    id="1",
                                    function=SimpleNamespace(
                                        name="search", arguments='{"q": "cut off'
                                    ),
                                )
                            ],
                        )
                    )
                ]
            ),
            SimpleNamespace(
                choices=[SimpleNamespace(delta=None, finish_reason="length")]
            ),
        ]
    )
    fake = _FakeClient([stream])
    monkeypatch.setattr("agent.provider.AsyncOpenAI", lambda **_: fake)
    provider = LLMProvider(api_key="k")

    with caplog.at_level("WARNING"):
        with pytest.raises(json.JSONDecodeError):
            await provider.chat(
                messages=[{"role": "user", "content": "hi"}],
                tools=[{"type": "function"}],
                model="m",
                max_tokens=10,
                on_content_delta=lambda chunk: _collect_delta([], chunk),
            )

    messages = [record.getMessage() for record in caplog.records]
    assert any("finish_reason=length" in message for message in messages)
    assert any('{"q": "cut off' in message for message in messages)


@pytest.mark.asyncio
async def test_tool_call_parse_failure_log_redacts_and_caps_raw_arguments(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
):
    """The raw arguments logged on a tool-call parse failure must not leak
    credential-shaped substrings or flood the log with unbounded text."""
    leaked_key = "sk-" + "b" * 40
    raw_arguments = "{" + leaked_key + " " + "y" * 1000
    fake = _FakeClient(
        [
            _Response(
                content=None,
                tool_calls=[_RawToolCall("1", "search", raw_arguments)],
                finish_reason="stop",
            )
        ]
    )
    monkeypatch.setattr("agent.provider.AsyncOpenAI", lambda **_: fake)
    provider = LLMProvider(api_key="k")

    with caplog.at_level("WARNING"):
        with pytest.raises(json.JSONDecodeError):
            await provider.chat(
                messages=[], tools=[{"type": "function"}], model="m", max_tokens=10
            )

    logged = "\n".join(record.getMessage() for record in caplog.records)
    assert leaked_key not in logged
    assert "REDACTED" in logged
    assert raw_arguments not in logged


@pytest.mark.asyncio
async def test_truncation_detection_is_case_insensitive_and_covers_max_tokens_alias(
    monkeypatch: pytest.MonkeyPatch,
):
    """#304 two-axis review, round 2: some OpenAI-compatible gateways report
    the cutoff as "MAX_TOKENS" (uppercase, and/or the "max_tokens" spelling
    rather than OpenAI's own "length"). An un-casefolded, "length"-only
    check would silently miss these and misdiagnose the exact truncation
    this issue exists to make visible."""
    fake = _FakeClient([_Response(content="", finish_reason="MAX_TOKENS")])
    monkeypatch.setattr("agent.provider.AsyncOpenAI", lambda **_: fake)
    provider = LLMProvider(api_key="k")

    result = await provider.chat(messages=[], tools=[], model="m", max_tokens=10)

    assert is_truncated_finish_reason(result.finish_reason) is True


@pytest.mark.asyncio
async def test_truncation_detection_still_rejects_unrelated_finish_reasons(
    monkeypatch: pytest.MonkeyPatch,
):
    fake = _FakeClient([_Response(content="ok", finish_reason="TOOL_CALLS")])
    monkeypatch.setattr("agent.provider.AsyncOpenAI", lambda **_: fake)
    provider = LLMProvider(api_key="k")

    result = await provider.chat(messages=[], tools=[], model="m", max_tokens=10)

    assert is_truncated_finish_reason(result.finish_reason) is False


@pytest.mark.asyncio
async def test_provider_level_warns_on_truncation_regardless_of_call_site(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
):
    """AC1: the provider layer itself must mark a truncated response, not
    just the couple of call sites (`fetch_role_mood`, the main-reply empty
    check in `reasoning_loop.py`) that happen to check `finish_reason`.
    Plenty of `LLMProvider.chat` callers (budget summaries, memory queries,
    proactive messaging) never look at `finish_reason` at all; this is the
    one line that still tells them something was cut off, regardless."""
    fake = _FakeClient([_Response(content="部分回", finish_reason="length")])
    monkeypatch.setattr("agent.provider.AsyncOpenAI", lambda **_: fake)
    provider = LLMProvider(api_key="k")

    with caplog.at_level("WARNING"):
        await provider.chat(messages=[], tools=[], model="my-model", max_tokens=10)

    messages = [record.getMessage() for record in caplog.records]
    assert any(
        "model=my-model" in message and "finish_reason=length" in message
        for message in messages
    )


@pytest.mark.asyncio
async def test_provider_level_does_not_warn_on_natural_stop(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
):
    fake = _FakeClient([_Response(content="完整回复", finish_reason="stop")])
    monkeypatch.setattr("agent.provider.AsyncOpenAI", lambda **_: fake)
    provider = LLMProvider(api_key="k")

    with caplog.at_level("WARNING"):
        await provider.chat(messages=[], tools=[], model="m", max_tokens=10)

    assert caplog.records == []


@pytest.mark.asyncio
async def test_provider_level_warns_on_truncation_for_streaming_path_too(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
):
    stream = _FakeStream(
        [
            SimpleNamespace(
                choices=[SimpleNamespace(delta=SimpleNamespace(content="部分"))]
            ),
            SimpleNamespace(
                choices=[SimpleNamespace(delta=None, finish_reason="length")]
            ),
        ]
    )
    fake = _FakeClient([stream])
    monkeypatch.setattr("agent.provider.AsyncOpenAI", lambda **_: fake)
    provider = LLMProvider(api_key="k")

    with caplog.at_level("WARNING"):
        await provider.chat(
            messages=[{"role": "user", "content": "hi"}],
            tools=[],
            model="my-stream-model",
            max_tokens=10,
            on_content_delta=lambda chunk: _collect_delta([], chunk),
        )

    messages = [record.getMessage() for record in caplog.records]
    assert any(
        "model=my-stream-model" in message and "finish_reason=length" in message
        for message in messages
    )
