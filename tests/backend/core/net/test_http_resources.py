import asyncio
import gzip
import ssl
from collections.abc import AsyncIterator, Iterator
from pathlib import Path

import certifi
import httpx
import pytest

from core.net.http import (
    HttpRequester,
    RetryPolicy,
    SharedHttpResources,
    shared_ssl_context,
)
from shiori_sdk.http import RequestBudget, ResponseTooLarge


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


class _TrackedStream(httpx.AsyncByteStream):
    def __init__(
        self,
        chunks: list[bytes],
        *,
        fail_after_read: bool = False,
        delay_s: float = 0.0,
    ):
        self.chunks = chunks
        self.fail_after_read = fail_after_read
        self.delay_s = delay_s
        self.read_count = 0
        self.closed = False

    async def __aiter__(self) -> AsyncIterator[bytes]:
        for chunk in self.chunks:
            if self.delay_s:
                await asyncio.sleep(self.delay_s)
            self.read_count += 1
            yield chunk
        if self.fail_after_read:
            raise httpx.ReadTimeout("stream timed out")

    async def aclose(self) -> None:
        self.closed = True


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("headers", "expected_reads"),
    [({"content-length": "20"}, 0), ({}, 2), ({"content-length": "1"}, 2)],
)
async def test_bounded_download_stops_and_closes_without_retrying(
    headers: dict[str, str], expected_reads: int
) -> None:
    stream = _TrackedStream([b"1234", b"5678", b"unread remainder"])
    calls: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        return httpx.Response(200, headers=headers, stream=stream)

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        requester = HttpRequester(client, RetryPolicy(), 1.0, RequestBudget(2.0))
        with pytest.raises(ResponseTooLarge) as caught:
            _ = await requester.get("https://example.com/file", max_response_bytes=5)

    assert caught.value.max_response_bytes == 5
    assert len(calls) == 1
    assert stream.read_count == expected_reads
    assert stream.closed


@pytest.mark.asyncio
async def test_bounded_download_limits_decoded_compressed_content() -> None:
    body = gzip.compress(b"a" * 1000)
    stream = _TrackedStream([body])

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            headers={"content-encoding": "gzip", "content-length": str(len(body))},
            stream=stream,
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        requester = HttpRequester(client, RetryPolicy(), 1.0, RequestBudget(2.0))
        with pytest.raises(ResponseTooLarge):
            _ = await requester.get("https://example.com/file", max_response_bytes=100)

    assert stream.closed


@pytest.mark.asyncio
async def test_bounded_download_preserves_decoded_body_and_response_metadata() -> None:
    body = "附件内容".encode("utf-8")
    stream = _TrackedStream([gzip.compress(body)])

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            201,
            headers={"content-encoding": "gzip", "content-type": "text/plain"},
            stream=stream,
            extensions={"http_version": b"HTTP/2"},
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        requester = HttpRequester(client, RetryPolicy(), 1.0, RequestBudget(2.0))
        response = await requester.get(
            "https://example.com/file", max_response_bytes=len(body)
        )

    assert response.status_code == 201
    assert response.content == body
    assert response.text == "附件内容"
    assert response.headers["content-encoding"] == "gzip"
    assert response.http_version == "HTTP/2"
    assert str(response.request.url) == "https://example.com/file"
    assert response.elapsed.total_seconds() >= 0
    assert response.is_closed
    assert stream.closed


@pytest.mark.asyncio
async def test_bounded_download_retries_stream_timeouts_with_original_timeout() -> None:
    streams = [
        _TrackedStream([b"first"], fail_after_read=True),
        _TrackedStream([b"second"]),
    ]
    calls: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        return httpx.Response(200, stream=streams[len(calls) - 1])

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        requester = HttpRequester(
            client,
            RetryPolicy(max_attempts=2, base_delay_s=0.0),
            1.0,
            RequestBudget(2.0),
        )
        response = await requester.get(
            "https://example.com/file", timeout_s=0.25, max_response_bytes=10
        )

    assert response.content == b"second"
    assert len(calls) == 2
    assert all(stream.closed for stream in streams)
    assert all(request.extensions["timeout"]["read"] == 0.25 for request in calls)


@pytest.mark.asyncio
async def test_bounded_download_total_budget_stops_continuous_stream() -> None:
    stream = _TrackedStream([b"x"] * 20, delay_s=0.01)
    calls: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        return httpx.Response(200, stream=stream)

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        requester = HttpRequester(client, RetryPolicy(), 1.0, RequestBudget(2.0))
        with pytest.raises(httpx.TimeoutException, match="request budget exhausted"):
            _ = await requester.get(
                "https://example.com/file",
                timeout_s=0.04,
                budget=RequestBudget(0.06),
                max_response_bytes=100,
            )

    assert len(calls) == 1
    assert 0 < stream.read_count < 20
    assert stream.closed


@pytest.mark.asyncio
async def test_bounded_download_total_budget_covers_redirect_chain() -> None:
    streams: list[_TrackedStream] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        await asyncio.sleep(0.01)
        stream = _TrackedStream([b"redirect"])
        streams.append(stream)
        return httpx.Response(302, headers={"location": "/next"}, stream=stream)

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        requester = HttpRequester(client, RetryPolicy(), 0.04, RequestBudget(0.06))
        with pytest.raises(httpx.TimeoutException, match="request budget exhausted"):
            _ = await requester.get(
                "https://example.com/file",
                follow_redirects=True,
                max_response_bytes=100,
            )

    assert 0 < len(streams) < client.max_redirects
    assert all(stream.closed for stream in streams)


@pytest.mark.asyncio
async def test_bounded_download_rejects_negative_limit_before_request() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise AssertionError("Invalid byte limits must not send requests")

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        requester = HttpRequester(client, RetryPolicy(), 1.0, RequestBudget(2.0))
        with pytest.raises(ValueError, match="nonnegative"):
            _ = await requester.get("https://example.com/file", max_response_bytes=-1)


@pytest.mark.asyncio
async def test_bounded_download_applies_cap_before_following_redirect() -> None:
    stream = _TrackedStream([b"too large", b"unread remainder"])
    calls: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        return httpx.Response(
            302, headers={"location": "https://example.com/next"}, stream=stream
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        requester = HttpRequester(client, RetryPolicy(), 1.0, RequestBudget(2.0))
        with pytest.raises(ResponseTooLarge):
            _ = await requester.get(
                "https://example.com/file", follow_redirects=True, max_response_bytes=5
            )

    assert len(calls) == 1
    assert stream.read_count == 1
    assert stream.closed


@pytest.mark.asyncio
@pytest.mark.parametrize("follow_redirects", [False, True])
async def test_bounded_download_preserves_redirect_control_and_history(
    follow_redirects: bool,
) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/file":
            return httpx.Response(302, headers={"location": "/next"}, content=b"moved")
        return httpx.Response(200, content=b"result")

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        requester = HttpRequester(client, RetryPolicy(), 1.0, RequestBudget(2.0))
        response = await requester.get(
            "https://example.com/file",
            follow_redirects=follow_redirects,
            max_response_bytes=6,
        )

    if follow_redirects:
        assert response.status_code == 200
        assert response.content == b"result"
        assert str(response.url) == "https://example.com/next"
        assert [item.content for item in response.history] == [b"moved"]
        assert response.next_request is None
    else:
        assert response.status_code == 302
        assert response.content == b"moved"
        assert response.history == []
        assert response.next_request is not None
        assert str(response.next_request.url) == "https://example.com/next"


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
