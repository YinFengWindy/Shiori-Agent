"""HTTP wire contracts: shared results, authentication, failures and cancellation."""

import asyncio
import json
import logging

import pytest
from shiori_sdk.mcp import McpToolError
from shiori_sdk.tools import ToolResult

from plugins.mcp.backend.http_session import HttpMcpSession
from plugins.mcp.backend.models import HttpTransport, LaunchCredentials, McpHttpError
from .http_peer import HttpPeer


def session(peer):
    return HttpMcpSession(
        "fixture",
        HttpTransport(auth="bearer"),
        LaunchCredentials(
            url=peer.url,
            bearer="private-bearer",
            headers={"X-API-Key": "private-header"},
        ),
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
            with pytest.raises((ConnectionError, McpHttpError)):
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
