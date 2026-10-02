"""HTTP request contracts; transport and retry policy remain host-owned."""

from dataclasses import dataclass
from typing import Protocol

import httpx


@dataclass(frozen=True)
class RequestBudget:
    """Wall-clock budget shared by all attempts of a request."""

    total_timeout_s: float


class HttpRequester(Protocol):
    """The bounded HTTP POST operation used by embedding engines."""

    async def post(
        self,
        url: str,
        *,
        headers: dict[str, str],
        json: dict[str, object],
        timeout_s: float,
        budget: RequestBudget,
    ) -> httpx.Response: ...


class HttpClient(Protocol):
    """External generation requests use the host-selected transport budget by default."""

    async def post(
        self,
        url: str,
        *,
        headers: dict[str, str],
        json: dict[str, object],
        timeout_s: float | None = None,
        budget: RequestBudget | None = None,
    ) -> httpx.Response: ...
    async def get(self, url: str, *, headers: dict[str, str]) -> httpx.Response: ...


class ChannelHttp(Protocol):
    """Budgeted transport for channel media and local platform services."""

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
    ) -> httpx.Response: ...
    async def get(
        self,
        url: str,
        *,
        headers: dict[str, str] | None = None,
        follow_redirects: bool = False,
        timeout_s: float | None = None,
        budget: RequestBudget | None = None,
    ) -> httpx.Response: ...


class HttpResources(Protocol):
    """Profiles share host-managed connections and are closed by their runtime owner."""

    @property
    def external_default(self) -> ChannelHttp: ...
    @property
    def local_service(self) -> ChannelHttp: ...
