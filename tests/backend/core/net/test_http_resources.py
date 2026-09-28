import asyncio
import ssl
from collections.abc import Iterator
from pathlib import Path

import certifi
import httpx
import pytest

from core.net.http import (
    HttpRequester,
    RequestBudget,
    RetryPolicy,
    SharedHttpResources,
    shared_ssl_context,
)


@pytest.fixture
def fresh_ssl_context() -> Iterator[None]:
    """Drops the process-wide context so each test observes its own creation."""
    shared_ssl_context.cache_clear()
    yield
    shared_ssl_context.cache_clear()


def _transport_ssl_contexts(client: httpx.AsyncClient) -> list[ssl.SSLContext]:
    """Collects the TLS context of the default transport and every proxy mount."""
    transports = [client._transport]
    transports.extend(t for t in client._mounts.values() if t is not None)
    contexts: list[ssl.SSLContext] = []
    for transport in transports:
        assert isinstance(transport, httpx.AsyncHTTPTransport)
        contexts.append(transport._pool._ssl_context)
    return contexts


@pytest.mark.asyncio
async def test_http_requester_retries_timeout_then_succeeds():
    calls = {"count": 0}

    def _handler(request: httpx.Request) -> httpx.Response:
        calls["count"] += 1
        if calls["count"] == 1:
            raise httpx.ReadTimeout("timeout", request=request)
        return httpx.Response(200, request=request, text="ok")

    client = httpx.AsyncClient(transport=httpx.MockTransport(_handler))
    requester = HttpRequester(
        client=client,
        retry_policy=RetryPolicy(max_attempts=2, base_delay_s=0.0, max_delay_s=0.0),
        default_timeout_s=1.0,
        default_budget=RequestBudget(total_timeout_s=2.0),
        sleep=lambda _: asyncio.sleep(0),
    )

    response = await requester.get("https://example.com")

    assert response.status_code == 200
    assert calls["count"] == 2
    await client.aclose()


@pytest.mark.asyncio
async def test_http_requester_retries_retryable_status_then_succeeds():
    calls = {"count": 0}

    def _handler(request: httpx.Request) -> httpx.Response:
        calls["count"] += 1
        if calls["count"] == 1:
            return httpx.Response(503, request=request, text="retry")
        return httpx.Response(200, request=request, text="ok")

    client = httpx.AsyncClient(transport=httpx.MockTransport(_handler))
    requester = HttpRequester(
        client=client,
        retry_policy=RetryPolicy(max_attempts=2, base_delay_s=0.0, max_delay_s=0.0),
        default_timeout_s=1.0,
        default_budget=RequestBudget(total_timeout_s=2.0),
        sleep=lambda _: asyncio.sleep(0),
    )

    response = await requester.get("https://example.com")

    assert response.status_code == 200
    assert calls["count"] == 2
    await client.aclose()


@pytest.mark.asyncio
async def test_shared_http_resources_aclose_is_idempotent():
    resources = SharedHttpResources()

    await resources.aclose()
    await resources.aclose()

    assert resources.closed is True


@pytest.mark.asyncio
async def test_shared_http_resources_load_certificates_once_including_proxies(
    fresh_ssl_context: None, monkeypatch: pytest.MonkeyPatch
):
    for name in ("SSL_CERT_FILE", "SSL_CERT_DIR", "NO_PROXY", "no_proxy"):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("HTTP_PROXY", "http://127.0.0.1:9")
    monkeypatch.setenv("HTTPS_PROXY", "http://127.0.0.1:9")
    created: list[ssl.SSLContext] = []
    create_default_context = ssl.create_default_context

    def counting_create_default_context(*args, **kwargs) -> ssl.SSLContext:
        context = create_default_context(*args, **kwargs)
        created.append(context)
        return context

    monkeypatch.setattr(ssl, "create_default_context", counting_create_default_context)

    first = SharedHttpResources()
    second = SharedHttpResources()
    try:
        contexts = [
            context
            for resources in (first, second)
            for client in resources._clients
            for context in _transport_ssl_contexts(client)
        ]
        # 2 resources x 3 clients x (default transport + http/https proxy mounts)
        assert len(contexts) == 18
        assert created == [shared_ssl_context()]
        assert all(context is created[0] for context in contexts)
    finally:
        await first.aclose()
        await second.aclose()


@pytest.mark.asyncio
async def test_shared_ssl_context_honors_ssl_cert_file(
    fresh_ssl_context: None, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
):
    bundle = Path(certifi.where()).read_text(encoding="utf-8")
    end = "-----END CERTIFICATE-----"
    first_ca = bundle[bundle.index("-----BEGIN") : bundle.index(end) + len(end)]
    single_ca = tmp_path / "single-ca.pem"
    single_ca.write_text(first_ca + "\n", encoding="utf-8")
    monkeypatch.setenv("SSL_CERT_FILE", str(single_ca))
    monkeypatch.delenv("SSL_CERT_DIR", raising=False)

    resources = SharedHttpResources()
    try:
        for client in resources._clients:
            for context in _transport_ssl_contexts(client):
                assert len(context.get_ca_certs()) == 1
    finally:
        await resources.aclose()
