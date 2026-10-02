"""Injected HTTP fixture that rejects unconfigured requests."""

import httpx
from shiori_sdk.http import RequestBudget


class FakeHttp:
    """Requests must be explicitly replaced by a fixture; never access the network."""

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

    async def get(self, url: str, *, headers: dict[str, str]) -> httpx.Response:
        """Fail at the injected transport boundary if a test forgot its response."""
        raise AssertionError(f"Unconfigured HTTP GET: {url}")
