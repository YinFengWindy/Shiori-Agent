"""Injected HTTP fixture that rejects unconfigured requests."""

import httpx
from collections.abc import Callable
from shiori_sdk.http import RequestBudget


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
    ) -> httpx.Response:
        """Fail at the injected transport boundary if a test forgot its response."""
        if self.handler is None:
            raise AssertionError(f"Unconfigured HTTP GET: {url}")
        request = httpx.Request("GET", url, headers=headers)
        self.requests.append(request)
        response = self.handler(request)
        response.request = request
        return response
