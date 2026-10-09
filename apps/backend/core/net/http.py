from __future__ import annotations

import asyncio
import random
import ssl
from dataclasses import dataclass, field
from datetime import timedelta
from functools import cache
from typing import Any, Literal

import httpx
from shiori_sdk.http import RequestBudget, ResponseTooLarge

HttpProfile = Literal["external_default", "feed_fetcher", "local_service"]


@cache
def shared_ssl_context() -> ssl.SSLContext:
    """Returns the process-wide TLS verification context for host HTTP clients.

    httpx builds a fresh context (reloading the CA bundle) for every transport,
    including the proxy transports it mounts from system proxy settings. This one
    is created once through httpx's own factory with its defaults, so
    ``SSL_CERT_FILE`` / ``SSL_CERT_DIR`` are honored exactly as httpx would, read
    when the first host client is built.

    Only for HTTP/1.1 clients: httpcore calls ``set_alpn_protocols`` on the context
    for every connection, mutating this shared object, so an ``http2=True`` client
    must build its own context instead of reusing this one.
    """
    return httpx.create_ssl_context()


@dataclass(frozen=True)
class RetryPolicy:
    max_attempts: int = 3
    retry_statuses: frozenset[int] = frozenset({408, 429, 500, 502, 503, 504})
    base_delay_s: float = 0.3
    max_delay_s: float = 1.5
    jitter_ratio: float = 0.2


@dataclass
class HttpRequester:
    client: httpx.AsyncClient
    retry_policy: RetryPolicy
    default_timeout_s: float
    default_budget: RequestBudget
    sleep: Any = asyncio.sleep

    async def request(
        self,
        method: str,
        url: str,
        *,
        headers: dict[str, str] | None = None,
        params: dict[str, Any] | None = None,
        content: bytes | str | None = None,
        json: Any = None,
        follow_redirects: bool = False,
        timeout_s: float | None = None,
        budget: RequestBudget | None = None,
        max_response_bytes: int | None = None,
    ) -> httpx.Response:
        if max_response_bytes is not None and max_response_bytes < 0:
            raise ValueError("max_response_bytes must be nonnegative")
        loop = asyncio.get_running_loop()
        deadline = loop.time() + (
            budget.total_timeout_s
            if budget is not None
            else self.default_budget.total_timeout_s
        )
        attempts = max(1, self.retry_policy.max_attempts)
        last_error: Exception | None = None
        response: httpx.Response | None = None
        method = method.upper()

        for attempt in range(1, attempts + 1):
            remaining = max(0.0, deadline - loop.time())
            if remaining <= 0:
                break
            try:
                response = await self._request_once(
                    method,
                    url,
                    max_response_bytes=max_response_bytes,
                    deadline=deadline,
                    headers=headers,
                    params=params,
                    content=content,
                    json=json,
                    follow_redirects=follow_redirects,
                    timeout=min(timeout_s or self.default_timeout_s, remaining),
                )
                if not self._should_retry_response(response, attempt, attempts):
                    return response
                await response.aread()
            except (httpx.TimeoutException, httpx.TransportError) as exc:
                last_error = exc
                if not self._should_retry_exception(exc, attempt, attempts):
                    raise

            sleep_s = min(
                self._backoff_seconds(attempt), max(0.0, deadline - loop.time())
            )
            if sleep_s <= 0:
                continue
            await self.sleep(sleep_s)

        if last_error is not None:
            raise last_error
        if response is None:
            raise httpx.TimeoutException("request budget exhausted")
        return response

    async def _request_once(
        self,
        method: str,
        url: str,
        *,
        max_response_bytes: int | None,
        deadline: float,
        **kwargs: Any,
    ) -> httpx.Response:
        if max_response_bytes is None:
            return await self.client.request(method, url, **kwargs)

        try:
            # httpx read timeouts measure inactivity. The shared absolute deadline
            # also bounds continuously arriving chunks and redirect chains.
            async with asyncio.timeout_at(deadline):
                follow_redirects = kwargs.pop("follow_redirects", False)
                request = self.client.build_request(method, url, **kwargs)
                history: list[httpx.Response] = []
                loop = asyncio.get_running_loop()
                while True:
                    if len(history) > self.client.max_redirects:
                        raise httpx.TooManyRedirects(
                            "Exceeded maximum allowed redirects.", request=request
                        )
                    # httpx's automatic redirects buffer intermediate response bodies.
                    # Follow explicitly so each downloaded body observes the same cap.
                    started = loop.time()
                    response = await self.client.send(
                        request, stream=True, follow_redirects=False
                    )
                    response.history = list(history)
                    buffered = await self._buffer_bounded_response(
                        response, max_response_bytes
                    )
                    buffered.elapsed = timedelta(seconds=loop.time() - started)
                    if not follow_redirects or buffered.next_request is None:
                        return buffered
                    request = buffered.next_request
                    history.append(buffered)
        except TimeoutError as exc:
            raise httpx.TimeoutException("request budget exhausted") from exc

    @staticmethod
    async def _buffer_bounded_response(
        response: httpx.Response, max_response_bytes: int
    ) -> httpx.Response:
        try:
            content_length = response.headers.get("content-length", "")
            if content_length.isdecimal() and int(content_length) > max_response_bytes:
                raise ResponseTooLarge(max_response_bytes)
            chunks: list[bytes] = []
            total_bytes = 0
            async for chunk in response.aiter_bytes():
                total_bytes += len(chunk)
                if total_bytes > max_response_bytes:
                    raise ResponseTooLarge(max_response_bytes)
                chunks.append(chunk)
        finally:
            await response.aclose()

        # The stream already decoded content encodings. Attach the original
        # headers only after construction so httpx does not decode it twice.
        buffered = httpx.Response(
            response.status_code,
            content=b"".join(chunks),
            request=response.request,
            extensions=response.extensions,
            history=response.history,
            default_encoding=response.default_encoding,
        )
        buffered.headers = response.headers
        buffered.next_request = response.next_request
        return buffered

    async def get(self, url: str, **kwargs: Any) -> httpx.Response:
        return await self.request("GET", url, **kwargs)

    async def post(self, url: str, **kwargs: Any) -> httpx.Response:
        return await self.request("POST", url, **kwargs)

    def _should_retry_response(
        self,
        response: httpx.Response,
        attempt: int,
        attempts: int,
    ) -> bool:
        return (
            attempt < attempts
            and response.status_code in self.retry_policy.retry_statuses
        )

    @staticmethod
    def _should_retry_exception(
        exc: Exception,
        attempt: int,
        attempts: int,
    ) -> bool:
        return attempt < attempts and isinstance(
            exc,
            (httpx.TimeoutException, httpx.TransportError),
        )

    def _backoff_seconds(self, attempt: int) -> float:
        delay = min(
            self.retry_policy.max_delay_s,
            self.retry_policy.base_delay_s * (2 ** max(0, attempt - 1)),
        )
        jitter = delay * self.retry_policy.jitter_ratio
        return max(0.0, delay + random.uniform(-jitter, jitter))


@dataclass
class SharedHttpResources:
    external_default: HttpRequester = field(init=False)
    feed_fetcher: HttpRequester = field(init=False)
    local_service: HttpRequester = field(init=False)
    _clients: list[httpx.AsyncClient] = field(init=False, default_factory=list)
    _closed: bool = field(init=False, default=False)

    def __post_init__(self) -> None:
        # All clients (and httpx's proxy transports) share one verification context.
        verify = shared_ssl_context()
        external_client = httpx.AsyncClient(
            verify=verify,
            limits=httpx.Limits(max_connections=20, max_keepalive_connections=10),
        )
        feed_client = httpx.AsyncClient(
            verify=verify,
            limits=httpx.Limits(max_connections=10, max_keepalive_connections=5),
        )
        local_client = httpx.AsyncClient(
            verify=verify,
            limits=httpx.Limits(max_connections=10, max_keepalive_connections=5),
        )
        self._clients = [external_client, feed_client, local_client]
        self.external_default = HttpRequester(
            client=external_client,
            retry_policy=RetryPolicy(max_attempts=3),
            default_timeout_s=30.0,
            default_budget=RequestBudget(total_timeout_s=45.0),
        )
        self.feed_fetcher = HttpRequester(
            client=feed_client,
            retry_policy=RetryPolicy(max_attempts=3, base_delay_s=0.2, max_delay_s=0.8),
            default_timeout_s=15.0,
            default_budget=RequestBudget(total_timeout_s=20.0),
        )
        self.local_service = HttpRequester(
            client=local_client,
            retry_policy=RetryPolicy(
                max_attempts=2, base_delay_s=0.15, max_delay_s=0.3
            ),
            default_timeout_s=5.0,
            default_budget=RequestBudget(total_timeout_s=8.0),
        )

    async def aclose(self) -> None:
        if self._closed:
            return
        first_error: Exception | None = None
        for client in reversed(self._clients):
            try:
                await client.aclose()
            except Exception as exc:
                if first_error is None:
                    first_error = exc
        self._closed = True
        if first_error is not None:
            raise first_error

    @property
    def closed(self) -> bool:
        return self._closed


_default_shared_http_resources: SharedHttpResources | None = None


def configure_default_shared_http_resources(
    resources: SharedHttpResources,
) -> None:
    global _default_shared_http_resources
    _default_shared_http_resources = resources


def clear_default_shared_http_resources(
    resources: SharedHttpResources | None = None,
) -> None:
    global _default_shared_http_resources
    if resources is None or _default_shared_http_resources is resources:
        _default_shared_http_resources = None


def get_default_shared_http_resources() -> SharedHttpResources:
    resources = _default_shared_http_resources
    if resources is None:
        raise RuntimeError("shared http resources not configured")
    return resources


def get_default_http_requester(profile: HttpProfile) -> HttpRequester:
    resources = get_default_shared_http_resources()
    return getattr(resources, profile)
