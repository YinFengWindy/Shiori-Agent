"""HTTP wire contracts: shared results, authentication, failures and cancellation."""

import asyncio
import json
import logging

import pytest
from shiori_mcp_client import McpToolError
from shiori_sdk.tools import ToolResult

from shiori_mcp_client import HttpMcpSession, McpHttpError
from shiori_mcp_client.testing_http import HttpPeer


def session(peer):
    return HttpMcpSession(
        "fixture",
        peer.url,
        headers={
            "Authorization": "Bearer private-bearer",
            "X-API-Key": "private-header",
        },
    )


@pytest.mark.parametrize("sse", [False, True])
async def test_http_discovers_all_pages_and_preserves_shared_results_and_headers(sse):
    async with HttpPeer(sse=sse) as peer:
        client = session(peer)
        try:
            infos = await client.connect()
            assert [info.name for info in infos] == peer.names
            assert await client.call("echo", {}) == "hello"
            image = await client.call("image", {})
            assert isinstance(image, ToolResult)
            assert (
                image.content_blocks[0]["image_url"]["url"]
                == "data:image/png;base64,aGVsbG8="
            )
            structured = await client.call("structured", {})
            assert isinstance(structured, ToolResult)
            assert structured.structured_content == {"records": [1, 2]}
            with pytest.raises(McpToolError) as caught:
                await client.call("rpc_error", {})
            assert caught.value.code == -32042
            with pytest.raises(McpToolError):
                await client.call("tool_error", {})
            assert peer.calls["rpc_error"] == peer.calls["tool_error"] == 1
        finally:
            await client.disconnect()
        assert all(
            target.endswith("?filter=read&key=query-canary")
            for _, target, _ in peer.requests
        )
        assert all(
            headers.get("authorization") == "Bearer private-bearer"
            and headers.get("x-api-key") == "private-header"
            for _, _, headers in peer.requests
        )
        assert any(method == "DELETE" for method, _, _ in peer.requests)
        assert client._owner.done()


async def test_modern_nonobject_structured_values_are_json_text_without_duplication():
    async with HttpPeer(modern=True) as peer:
        client = session(peer)
        try:
            await client.connect()
            assert json.loads(await client.call("json_list", {})) == [1, 2]
            assert await client.call("json_scalar", {}) == "42"
            assert await client.call("json_null", {}) == "null"
            assert await client.call("echo", {}) == "hello"
        finally:
            await client.disconnect()


@pytest.mark.parametrize("status", [401, 403])
async def test_http_auth_failure_has_status_without_body_or_query_in_logs(
    status, caplog
):
    caplog.set_level(logging.DEBUG)
    async with HttpPeer() as peer:
        peer.status = status
        client = session(peer)
        with pytest.raises(McpHttpError, match=str(status)):
            await client.connect()
        await client.disconnect()
        assert client._owner.done()
        for secret in ("private-bearer", "private-header", "query-canary"):
            assert secret not in caplog.text


async def test_call_cancellation_timeout_and_disconnect_never_replay():
    async with HttpPeer(sse=True) as peer:
        client = session(peer)
        await client.connect()
        try:
            call = asyncio.create_task(client.call("wait", {}, timeout=180))
            await asyncio.wait_for(peer.waiting.wait(), 2)
            call.cancel()
            with pytest.raises(asyncio.CancelledError):
                await call
            assert peer.calls["wait"] == 1
            with pytest.raises(TimeoutError):
                await client.call("wait", {}, timeout=0.05)
            assert peer.calls["wait"] == 2
            peer.release.set()
            assert await client.call("echo", {}) == "hello"
            with pytest.raises((McpToolError, McpHttpError)):
                # The official HTTP SDK synthesizes an error response here.
                # Its origin is ambiguous, so it cannot authorize a retry.
                await client.call("drop", {})
            assert peer.calls["drop"] == 1
        finally:
            await client.disconnect()
        assert client._owner.done()
        with pytest.raises(ConnectionError):
            await client.call("echo", {})


async def test_disconnect_closes_cancelled_request_without_waiting_for_remote_work():
    async with HttpPeer(sse=True) as peer:
        client = session(peer)
        await client.connect()
        call = asyncio.create_task(client.call("wait", {}, timeout=180))
        await asyncio.wait_for(peer.waiting.wait(), 2)
        call.cancel()
        with pytest.raises(asyncio.CancelledError):
            await call
        await asyncio.wait_for(client.disconnect(), 2)
        assert client._owner.done()
        assert peer.calls["wait"] == 1


async def test_call_deadline_includes_queued_send_and_prevents_late_dispatch():
    class NotificationDelayPeer(HttpPeer):
        def __init__(self):
            super().__init__(sse=True)
            self.hold_notifications = False
            self.notification_seen = asyncio.Event()
            self.notification_release = asyncio.Event()

        async def _reply(self, writer, status, body, *, sse=False):
            if status == 202 and self.hold_notifications:
                self.notification_seen.set()
                await self.notification_release.wait()
            return await super()._reply(writer, status, body, sse=sse)

    async with NotificationDelayPeer() as peer:
        client = session(peer)
        await client.connect()
        following = None
        try:
            peer.hold_notifications = True
            old = asyncio.create_task(client.call("wait", {}, timeout=180))
            await asyncio.wait_for(peer.waiting.wait(), 2)
            old.cancel()
            with pytest.raises(asyncio.CancelledError):
                await old
            await asyncio.wait_for(peer.notification_seen.wait(), 2)
            following = asyncio.create_task(client.call("echo", {}, timeout=0.05))
            # Let the real deadline expire while the writer is blocked. The
            # SDK may still be completing its bounded cancellation notification.
            await asyncio.sleep(0.15)
            assert not peer.notification_release.is_set()
            assert peer.calls["echo"] == 0
            peer.notification_release.set()
            with pytest.raises(TimeoutError):
                await asyncio.wait_for(following, 2)
            peer.release.set()
            # A completed later request proves the writer advanced past the
            # cancelled queue item without dispatching its tool after timeout.
            await client.call("structured", {})
            assert peer.calls["echo"] == 0
            assert peer.calls["wait"] == 1
        finally:
            peer.notification_release.set()
            peer.release.set()
            if following is not None:
                if not following.done():
                    following.cancel()
                await asyncio.gather(following, return_exceptions=True)
            await asyncio.wait_for(client.disconnect(), 3)
        assert client._owner.done()


async def test_auth_provider_intent_survives_sdk_groups_and_http_rejection(caplog):
    import httpx2
    from shiori_mcp_client import McpAuthenticationRequired

    class LoginRequired(McpAuthenticationRequired):
        pass

    class Provider(httpx2.Auth):
        async def async_auth_flow(self, request):
            response = yield request
            assert response.status_code == 401
            raise ExceptionGroup(
                "unsafe OAuth failure",
                [ConnectionError("unsafe token response"), LoginRequired("需要登录")],
            )

    caplog.set_level(logging.DEBUG)
    async with HttpPeer() as peer:
        peer.status = 401
        provider = Provider()
        client = HttpMcpSession("auth", peer.url, auth=provider)
        with pytest.raises(LoginRequired, match="需要登录"):
            await client.connect()
        assert client._owner.done()
        assert not any(
            value in caplog.text
            for value in (
                "unsafe OAuth failure",
                "unsafe token response",
                "query-canary",
            )
        )


@pytest.mark.parametrize("code", [-32000, -32001])
async def test_http_remote_reserved_codes_preserve_message_data_without_replay(code):
    class ErrorPeer(HttpPeer):
        async def _rpc(self, request):
            if request["method"] == "tools/call":
                self.calls["rpc_error"] += 1
                return {
                    "error": {
                        "code": code,
                        "message": "remote business failure",
                        "data": {"detail": 42},
                    }
                }
            return await super()._rpc(request)

    async with ErrorPeer() as peer:
        client = session(peer)
        try:
            await client.connect()
            with pytest.raises(McpToolError) as caught:
                await client.call("rpc_error", {})
            assert (caught.value.code, caught.value.message, caught.value.data) == (
                code,
                "remote business failure",
                {"detail": 42},
            )
            assert peer.calls["rpc_error"] == 1
            assert client._observation.calls == {}
        finally:
            await client.disconnect()


async def test_truncated_http_reply_is_not_assumed_to_be_a_retryable_disconnect():
    class TruncatedPeer(HttpPeer):
        truncate = False

        async def _rpc(self, request):
            if request["method"] == "tools/call":
                self.truncate = True
            return await super()._rpc(request)

        async def _reply(self, writer, status, body, *, sse=False):
            if self.truncate and status == 200:
                writer.write(
                    b"HTTP/1.1 200 OK\r\nContent-Type: application/json\r\nContent-Length: 999\r\nConnection: close\r\n\r\n{"
                )
                await writer.drain()
                return
            await super()._reply(writer, status, body, sse=sse)

    async with TruncatedPeer() as peer:
        client = session(peer)
        try:
            await client.connect()
            with pytest.raises(McpToolError) as caught:
                await client.call("echo", {})
            assert caught.value.code == -32000
            assert peer.calls["echo"] == 1
            assert client._observation.calls == {}
        finally:
            peer.truncate = False
            await client.disconnect()
