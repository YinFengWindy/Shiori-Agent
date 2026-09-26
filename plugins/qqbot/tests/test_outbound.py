"""Outbound stream updates and safe fallback through a simulated QQ API."""

from __future__ import annotations

import asyncio
import json

import httpx
import pytest

from plugins.qqbot.backend.channel import QQBotChannel


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("failure", "fail_at", "recall_fails", "should_raise"),
    [
        (None, 0, False, False),
        (400, 0, False, False),
        (400, 1, False, False),
        (400, 1, True, True),
        (408, 0, False, True),
        (500, 0, False, True),
        ("timeout", 0, False, True),
        ("timeout", 1, False, True),
        ("missing_id", 0, False, True),
    ],
)
async def test_send_stream_preserves_one_message_or_requires_confirmed_cleanup(
    failure: int | str | None, fail_at: int, recall_fails: bool, should_raise: bool
) -> None:
    calls: list[tuple[str, str, dict]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/app/getAppAccessToken":
            return httpx.Response(200, json={"access_token": "tok", "expires_in": 7200})
        body = json.loads(request.content) if request.content else {}
        calls.append((request.method, request.url.path, body))
        if request.url.path.endswith("/stream_messages"):
            if body["index"] >= fail_at and failure is not None:
                if failure == "timeout":
                    raise httpx.ReadTimeout("response lost", request=request)
                if failure == "missing_id":
                    return httpx.Response(200, json={})
                assert isinstance(failure, int)
                return httpx.Response(failure)
            return httpx.Response(200, json={"id": "stream-1"})
        if request.method == "DELETE" and recall_fails:
            return httpx.Response(500)
        return httpx.Response(200, json={"id": "normal-1"})

    channel = QQBotChannel("app", "secret")
    await channel._client.aclose()
    channel._client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    channel._last_c2c_msg_id["user-1"] = "inbound-1"
    message = "分段内容" * 90
    try:
        if should_raise:
            with pytest.raises((httpx.HTTPError, RuntimeError)):
                await channel.send_stream("c2c:user-1", message)
        else:
            await channel.send_stream("c2c:user-1", message)
        ordinary = [body for method, path, body in calls if path.endswith("/messages")]
        if should_raise or failure is None:
            assert ordinary == []
        else:
            assert [body["markdown"]["content"] for body in ordinary] == [message]
            if fail_at:
                assert calls[-2][:2] == ("DELETE", "/v2/users/user-1/messages/stream-1")
        streams = [body for _, path, body in calls if path.endswith("/stream_messages")]
        if failure is None:
            assert [body.get("stream_msg_id") for body in streams] == [
                None,
                "stream-1",
                "stream-1",
            ]
            assert [body["index"] for body in streams] == [0, 1, 2]
            assert streams[-1]["input_state"] == 10
            assert streams[-1]["content_raw"] == message
    finally:
        await channel._client.aclose()


@pytest.mark.asyncio
async def test_push_recovers_rejected_continuation_in_place() -> None:
    bodies: list[dict] = []

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/app/getAppAccessToken":
            return httpx.Response(200, json={"access_token": "tok", "expires_in": 7200})
        assert request.url.path.endswith("/stream_messages")
        body = json.loads(request.content)
        bodies.append(body)
        if len(bodies) == 2:
            return httpx.Response(429)
        return httpx.Response(200, json={"id": "stream-1"})

    channel = QQBotChannel("app", "secret")
    await channel._client.aclose()
    channel._client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    channel._last_c2c_msg_id["user-1"] = "inbound-1"
    message = "分段内容" * 90
    try:
        await channel.send_stream("c2c:user-1", message)
        assert [(b["index"], b["input_state"]) for b in bodies] == [
            (0, 1),
            (1, 1),
            (1, 10),
        ]
        assert bodies[-1]["stream_msg_id"] == "stream-1"
        assert bodies[-1]["content_raw"] == message
    finally:
        await channel._client.aclose()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("cancel_index", "recall_fails"), [(0, False), (1, False), (2, False), (1, True)]
)
async def test_cancelled_push_recalls_only_acknowledged_incomplete_stream(
    cancel_index: int, recall_fails: bool, caplog: pytest.LogCaptureFixture
) -> None:
    entered = asyncio.Event()
    release = asyncio.Event()
    calls: list[tuple[str, str, dict]] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/app/getAppAccessToken":
            return httpx.Response(200, json={"access_token": "tok", "expires_in": 7200})
        body = json.loads(request.content) if request.content else {}
        calls.append((request.method, request.url.path, body))
        if request.url.path.endswith("/stream_messages"):
            if body["index"] == cancel_index:
                entered.set()
                await release.wait()
            return httpx.Response(200, json={"id": "stream-1"})
        assert request.method == "DELETE"
        return httpx.Response(500 if recall_fails else 200)

    channel = QQBotChannel("app", "secret")
    await channel._client.aclose()
    channel._client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    channel._last_c2c_msg_id["user-1"] = "inbound-1"
    push = asyncio.create_task(channel.send_stream("c2c:user-1", "分段内容" * 90))
    try:
        await asyncio.wait_for(entered.wait(), 1)
        push.cancel()
        release.set()
        with pytest.raises(asyncio.CancelledError):
            await asyncio.wait_for(push, 1)
        streams = [body for _, path, body in calls if path.endswith("/stream_messages")]
        assert [body["index"] for body in streams] == list(range(cancel_index + 1))
        deletes = [(method, path) for method, path, _ in calls if method == "DELETE"]
        assert deletes == (
            [("DELETE", "/v2/users/user-1/messages/stream-1")]
            if cancel_index < 2
            else []
        )
        assert not any(path.endswith("/messages") for _, path, _ in calls)
        if recall_fails:
            assert "取消投递后撤回流式预览失败" in caplog.text
    finally:
        release.set()
        await channel._client.aclose()
