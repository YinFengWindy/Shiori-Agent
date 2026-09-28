from __future__ import annotations

import httpx
import pytest

from plugins.qq.backend.accounts_avatar import fetch_qq_avatar

_PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 8


@pytest.mark.asyncio
async def test_avatar_is_fetched_for_the_qq_number_as_a_data_uri():
    seen: list[str] = []

    def handle(request: httpx.Request) -> httpx.Response:
        seen.append(str(request.url))
        return httpx.Response(200, content=_PNG)

    avatar = await fetch_qq_avatar("101", transport=httpx.MockTransport(handle))

    assert seen == ["https://q1.qlogo.cn/g?b=qq&nk=101&s=100"]
    assert avatar is not None and avatar.startswith("data:image/png;base64,")


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "response",
    [httpx.Response(502), httpx.Response(200, content=b"<html>")],
)
async def test_unusable_avatar_responses_are_reported_as_unavailable(response):
    transport = httpx.MockTransport(lambda _request: response)

    assert await fetch_qq_avatar("101", transport=transport) is None
