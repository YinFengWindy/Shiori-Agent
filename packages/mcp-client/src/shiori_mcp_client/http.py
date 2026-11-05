"""Streamable HTTP transport independent of plugin settings and credential storage."""

from collections.abc import Mapping
from contextlib import asynccontextmanager
import httpx2
from mcp.client._transport import Transport
from mcp.client.streamable_http import streamable_http_client
from .session import ClientSession, _HTTP_STATUS
from .result import result_payload


class HttpMcpSession(ClientSession):
    """An eager HTTP session with a caller-owned optional authentication provider."""

    def __init__(
        self,
        server: str,
        url: str,
        *,
        headers: Mapping[str, str] | None = None,
        auth: httpx2.Auth | None = None,
        connect_timeout: float = 15.0,
    ):
        super().__init__(server, connect_timeout=connect_timeout)
        self._url, self._headers, self._auth = url, dict(headers or {}), auth

    _result_payload = staticmethod(result_payload)

    def _transport(self) -> Transport:
        return self._http_transport()

    @asynccontextmanager
    async def _http_transport(self):
        async with httpx2.AsyncClient(
            headers=self._headers,
            auth=self._auth,
            timeout=httpx2.Timeout(15.0, read=300.0),
            follow_redirects=False,
            event_hooks={"request": [self._request], "response": [self._response]},
        ) as http:
            async with streamable_http_client(
                self._url, http_client=http, max_sse_event_size=20 * 1024 * 1024
            ) as streams:
                yield streams

    @staticmethod
    async def _request(request: httpx2.Request) -> None:
        if request.method == "DELETE":
            request.extensions["timeout"] = httpx2.Timeout(2.0).as_dict()

    @staticmethod
    async def _response(response: httpx2.Response) -> None:
        statuses = _HTTP_STATUS.get()
        if statuses is not None:
            statuses.append(response.status_code)
