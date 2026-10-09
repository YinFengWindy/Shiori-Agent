"""HTTP request contracts; transport and retry policy remain host-owned."""

from dataclasses import dataclass
from typing import Protocol

import httpx


@dataclass(frozen=True)
class RequestBudget:
    """Wall-clock budget shared by all attempts of a request."""

    total_timeout_s: float


class ResponseTooLarge(ValueError):
    """A download exceeded its declared or decoded response byte limit."""

    def __init__(self, max_response_bytes: int):
        self.max_response_bytes = max_response_bytes
        super().__init__(f"HTTP response exceeds {max_response_bytes} bytes")


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


class HttpGet(Protocol):
    """Bounded downloads share the owning host transport and connection pool."""

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
        """Read a response, raising ResponseTooLarge above the optional byte cap.

        The cap must be nonnegative and applies to the advertised Content-Length
        and decoded body as it streams. Rejected responses are closed, not retried.
        Capped downloads enforce the shared wall-clock budget across redirects
        and retries, even when body chunks arrive continuously.
        """
        ...


class HttpClient(HttpGet, Protocol):
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


class ChannelHttp(HttpGet, Protocol):
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
        max_response_bytes: int | None = None,
    ) -> httpx.Response:
        """Issue a request using the same optional response byte cap as get."""
        ...


class HttpResources(Protocol):
    """Profiles share host-managed connections and are closed by their runtime owner."""

    @property
    def external_default(self) -> ChannelHttp: ...
    @property
    def local_service(self) -> ChannelHttp: ...
