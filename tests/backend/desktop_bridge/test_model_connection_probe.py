from __future__ import annotations

from typing import Any

import pytest

from desktop_bridge.model_connection_probe import probe_model_connection
from desktop_bridge.request_router import DesktopBridgeRequestRouter


class _FakeProvider:
    """Records construction and the single probe call; never touches the network."""

    def __init__(self, outcome: BaseException | None = None, **kwargs: Any) -> None:
        self.kwargs = kwargs
        self.outcome = outcome
        self.calls: list[dict[str, Any]] = []
        self.closed = False

    async def chat(self, **kwargs: Any) -> object:
        self.calls.append(kwargs)
        if self.outcome is not None:
            raise self.outcome
        return object()

    async def aclose(self) -> None:
        self.closed = True


def _factory(outcome: BaseException | None = None):
    created: list[_FakeProvider] = []

    def build(**kwargs: Any) -> _FakeProvider:
        provider = _FakeProvider(outcome, **kwargs)
        created.append(provider)
        return provider

    return build, created


_DRAFT = {
    "provider": "deepseek",
    "model": "deepseek-chat",
    "base_url": "https://api.deepseek.com",
    "api_key": "draft-key-value",
}


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "capacity_draft",
    [
        {},
        {"context_window_tokens": None, "max_output_tokens": None},
        {"context_window_tokens": 0, "max_output_tokens": 0},
    ],
)
async def test_probe_sends_one_tiny_request_with_the_draft_connection(
    capacity_draft,
) -> None:
    build, created = _factory()

    result = await probe_model_connection(
        {**_DRAFT, **capacity_draft}, provider_factory=build
    )

    assert result["ok"] is True
    assert isinstance(result["latency_ms"], int)
    [provider] = created
    assert provider.kwargs["api_key"] == "draft-key-value"
    assert provider.kwargs["base_url"] == "https://api.deepseek.com"
    assert provider.kwargs["provider_name"] == "deepseek"
    assert provider.kwargs["max_retries"] == 0
    assert provider.kwargs["payload_snapshot_enabled"] is False
    [call] = provider.calls
    assert call["model"] == "deepseek-chat"
    assert call["max_tokens"] <= 8
    assert call["tools"] == []
    assert provider.closed


@pytest.mark.asyncio
async def test_probe_failure_is_a_result_scrubbed_of_the_submitted_key() -> None:
    # The upstream echoes the exact key, in a shape redact_secrets cannot name.
    build, created = _factory(
        RuntimeError("401 Incorrect API key provided: draft-key-value\ntrace")
    )

    result = await probe_model_connection(_DRAFT, provider_factory=build)

    assert result["ok"] is False
    assert "draft-key-value" not in result["message"]
    assert result["detail"].startswith("RuntimeError: 401 Incorrect API key")
    assert "trace" not in result["message"]
    assert created[0].closed


@pytest.mark.asyncio
async def test_probe_failure_scrubs_credential_shaped_text() -> None:
    build, _ = _factory(
        RuntimeError(
            "denied Authorization: Bearer abcdefghijklmnop sk-live-123456789012"
        )
    )

    result = await probe_model_connection(_DRAFT, provider_factory=build)

    assert "abcdefghijklmnop" not in result["message"]
    assert "123456789012" not in result["message"]


@pytest.mark.asyncio
async def test_probe_timeout_reports_the_deadline() -> None:
    build, _ = _factory(TimeoutError())

    result = await probe_model_connection(_DRAFT, provider_factory=build, timeout_s=5)

    assert result["ok"] is False
    assert result["code"] == "timeout"
    assert "5 秒" in result["message"]


@pytest.mark.asyncio
async def test_probe_rejects_incomplete_drafts_before_any_request() -> None:
    build, created = _factory()

    with pytest.raises(ValueError, match="模型、API Key"):
        await probe_model_connection(
            {**_DRAFT, "model": " ", "api_key": ""}, provider_factory=build
        )

    assert created == []


@pytest.mark.asyncio
async def test_probe_allows_a_keyless_local_endpoint() -> None:
    build, created = _factory()

    result = await probe_model_connection(
        {**_DRAFT, "api_key": "", "base_url": "http://localhost:11434/v1"},
        provider_factory=build,
    )

    assert result["ok"] is True
    assert created[0].kwargs["base_url"] == "http://localhost:11434/v1"


@pytest.mark.asyncio
async def test_router_serves_models_test_without_domain_handlers(monkeypatch) -> None:
    seen: list[dict[str, Any]] = []

    async def fake_probe(payload: dict[str, Any]) -> dict[str, Any]:
        seen.append(payload)
        return {"ok": True, "latency_ms": 1}

    monkeypatch.setattr(
        "desktop_bridge.request_router.probe_model_connection", fake_probe
    )
    router = DesktopBridgeRequestRouter(
        roles=None,  # type: ignore[arg-type]
        sessions_and_tasks=None,  # type: ignore[arg-type]
        chat=None,  # type: ignore[arg-type]
        voice=None,  # type: ignore[arg-type]
        plugins=None,  # type: ignore[arg-type]
    )

    result = await router.dispatch(
        "models.test", _DRAFT, request_id="r", emit_event=lambda _event: None
    )

    assert result == {"ok": True, "latency_ms": 1}
    assert seen == [_DRAFT]


@pytest.mark.asyncio
async def test_probe_timeout_scrubs_the_exact_submitted_key() -> None:
    import httpx

    build, _ = _factory(httpx.ReadTimeout("request with draft-key-value timed out"))
    result = await probe_model_connection(_DRAFT, provider_factory=build)
    assert result["code"] == "timeout"
    assert "draft-key-value" not in str(result)
    assert "ReadTimeout" in result["detail"]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "status,code,remedy",
    [
        (401, "credentials", "密钥"),
        (403, "permission", "授权"),
        (404, "model", "模型名称"),
        (429, "rate_limit", "服务商限制"),
        (503, "upstream", "稍后重试"),
    ],
)
async def test_probe_reports_the_remedy_for_the_actual_status(status, code, remedy):
    import httpx
    import openai

    response = httpx.Response(
        status, request=httpx.Request("POST", "https://example.com")
    )
    build, _ = _factory(
        openai.APIStatusError("upstream diagnostic", response=response, body=None)
    )
    result = await probe_model_connection(_DRAFT, provider_factory=build)
    assert result["code"] == code
    assert remedy in result["message"]
    assert "upstream diagnostic" in result["detail"]
