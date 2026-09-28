from __future__ import annotations

import time

import httpx
import pytest

from plugins.qqbot.backend.account_avatar import fetch_bot_avatar
from plugins.qqbot.backend.channel import QQBotChannel
from plugins.qqbot.backend.gateway import _TokenCache


def _channel(handle) -> QQBotChannel:
    channel = QQBotChannel("100", "secret")
    channel._token = _TokenCache("token", time.time() + 7200)
    channel._client = httpx.AsyncClient(transport=httpx.MockTransport(handle))
    return channel


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("image", "expected"),
    [
        (httpx.Response(200, content=bytes.fromhex("89504e470d0a1a0a")), "png"),
        (httpx.Response(404), None),
    ],
)
async def test_avatar_comes_from_the_bots_own_profile(image, expected):
    def handle(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/users/@me":
            assert request.headers["Authorization"] == "QQBot token"
            return httpx.Response(200, json={"avatar": "https://cdn.test/bot.png"})
        assert str(request.url) == "https://cdn.test/bot.png"
        return image

    channel = _channel(handle)
    try:
        avatar = await fetch_bot_avatar(channel)
    finally:
        await channel._close_http_client()

    if expected is None:
        assert avatar is None
    else:
        assert avatar == "data:image/png;base64,iVBORw0KGgo="


@pytest.mark.asyncio
async def test_bot_without_avatar_has_an_empty_one():
    channel = _channel(lambda _request: httpx.Response(200, json={"id": "1"}))
    try:
        assert await fetch_bot_avatar(channel) == ""
    finally:
        await channel._close_http_client()
