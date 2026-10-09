"""Injected HTTP fixture that rejects unconfigured requests."""

import httpx
from collections.abc import Callable
from shiori_sdk.http import RequestBudget, ResponseTooLarge


class FakeHttp:
    """Requests must be explicitly replaced by a fixture; never access the network."""

    def __init__(
        self, handler: Callable[[httpx.Request], httpx.Response] | None = None
    ):
        self.handler = handler
        self.requests: list[httpx.Request] = []

    async def post(
        self,
        url: str,
        *,
        headers: dict[str, str],
        json: dict[str, object],
        timeout_s: float | None = None,
        budget: RequestBudget | None = None,
    ) -> httpx.Response:
        """Fail at the injected transport boundary if a test forgot its response."""
        raise AssertionError(f"Unconfigured HTTP POST: {url}")

    async def get(
        self,
        url: str,
        *,
        headers: dict[str, str] | None = None,
        follow_redirects: bool = False,
        timeout_s: float | None = None,
        budget: RequestBudget | None = None,
        max_response_bytes: int | None = None,
    ) -> httpx.Response:
        """Fail at the injected transport boundary if a test forgot its response."""
        return self._dispatch("GET", url, headers, max_response_bytes)

    def _dispatch(
        self,
        method: str,
        url: str,
        headers: dict[str, str] | None,
        max_response_bytes: int | None = None,
    ) -> httpx.Response:
        """Record the request and answer it with the fixture's handler."""
        if max_response_bytes is not None and max_response_bytes < 0:
            raise ValueError("max_response_bytes must be nonnegative")
        if self.handler is None:
            raise AssertionError(f"Unconfigured HTTP {method}: {url}")
        request = httpx.Request(method, url, headers=headers)
        self.requests.append(request)
        response = self.handler(request)
        response.request = request
        if max_response_bytes is not None:
            content_length = response.headers.get("content-length", "")
            if (
                content_length.isdecimal() and int(content_length) > max_response_bytes
            ) or len(response.content) > max_response_bytes:
                raise ResponseTooLarge(max_response_bytes)
        return response


class FakeChannelHttp(FakeHttp):
    """Channel transport profile that answers only through a configured handler."""

    async def request(
        self,
        method: str,
        url: str,
        *,
        headers: dict[str, str] | None = None,
        params: dict[str, object] | None = None,
        content: bytes | str | None = None,
        json: object = None,
        follow_redirects: bool = False,
        timeout_s: float | None = None,
        budget: RequestBudget | None = None,
        max_response_bytes: int | None = None,
    ) -> httpx.Response:
        """Fail at the injected transport boundary if a test forgot its response."""
        return self._dispatch(method, url, headers, max_response_bytes)


class FakeHttpResources:
    """The host's channel HTTP profiles, each refusing unconfigured requests."""

    def __init__(
        self,
        *,
        external_default: FakeChannelHttp | None = None,
        local_service: FakeChannelHttp | None = None,
    ):
        self.external_default = (
            external_default if external_default is not None else FakeChannelHttp()
        )
        self.local_service = (
            local_service if local_service is not None else FakeChannelHttp()
        )
