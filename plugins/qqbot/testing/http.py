"""Official QQBot HTTP responses shared by plugin and host integration tests."""

import json

import httpx

STREAM_PATH = "/v2/users/user-1/stream_messages"
MESSAGE_PATH = "/v2/users/user-1/messages"


class QQBotHttp:
    """Records requests and models stream expiry for one test recipient."""

    def __init__(self) -> None:
        self.calls: list[tuple[str, str, dict[str, object]]] = []
        self.fail_stream_from: int | None = None

    def handler(self, request: httpx.Request) -> httpx.Response:
        """Answer authentication, discovery and message requests without network IO."""
        if request.url.path == "/app/getAppAccessToken":
            return httpx.Response(200, json={"access_token": "tok", "expires_in": 7200})
        if request.url.path == "/gateway":
            return httpx.Response(200, json={"url": "wss://gateway.invalid"})
        body = json.loads(request.content) if request.content else {}
        assert isinstance(body, dict)
        self.calls.append((request.method, request.url.path, body))
        if request.url.path == STREAM_PATH:
            if (
                self.fail_stream_from is not None
                and len(self.stream_bodies()) > self.fail_stream_from
            ):
                return httpx.Response(400, json={"message": "stream expired"})
            return httpx.Response(200, json={"id": "stream-1"})
        return httpx.Response(200, json={})

    def stream_bodies(self) -> list[dict[str, object]]:
        """Return stream payloads in their request order, including rejected calls."""
        return [body for _method, path, body in self.calls if path == STREAM_PATH]

    def markdown_messages(self) -> list[str]:
        """Return final Markdown content sent through the ordinary message API."""
        messages: list[str] = []
        for method, path, body in self.calls:
            if method == "POST" and path == MESSAGE_PATH and "markdown" in body:
                markdown = body["markdown"]
                assert isinstance(markdown, dict)
                content = markdown["content"]
                assert isinstance(content, str)
                messages.append(content)
        return messages
