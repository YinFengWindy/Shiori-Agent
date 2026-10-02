from __future__ import annotations

import io

import httpx
import pytest
from shiori_sdk.testing.avatars import FakeAvatars
from shiori_sdk.testing.http import FakeHttp
from PIL import Image

import plugins.qq.backend.accounts_avatar as accounts_avatar
from plugins.qq.backend.accounts_avatar import fetch_qq_avatar, refresh_message_avatars
from plugins.qq.backend.accounts_inbound import inbound_message

_PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 8


@pytest.mark.asyncio
async def test_avatar_is_fetched_for_the_qq_number_as_a_data_uri():
    seen: list[str] = []

    def handle(request: httpx.Request) -> httpx.Response:
        seen.append(str(request.url))
        return httpx.Response(200, content=_PNG)

    avatar = await fetch_qq_avatar("101", requester=FakeHttp(handle))

    assert seen == ["https://q1.qlogo.cn/g?b=qq&nk=101&s=100"]
    assert avatar is not None and avatar.startswith("data:image/png;base64,")


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "response",
    [httpx.Response(502), httpx.Response(200, content=b"<html>")],
)
async def test_unusable_avatar_responses_are_reported_as_unavailable(response):
    requester = FakeHttp(lambda _request: response)

    assert await fetch_qq_avatar("101", requester=requester) is None


def _picture() -> bytes:
    output = io.BytesIO()
    Image.new("RGB", (8, 8), "pink").save(output, format="PNG")
    return output.getvalue()


def _message(kind: str):
    message = inbound_message(
        account_id="account-b",
        expected_uin="202",
        via_account={},
        event={
            "post_type": "message",
            "message_type": kind,
            "self_id": 202,
            "group_id": 777,
            "user_id": 902,
            "raw_message": "hello",
        },
    )
    assert message is not None
    return message


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("kind", "chat_id", "chat_url"),
    [
        ("group", "gqq:777", "https://p.qlogo.cn/gh/777/777/100"),
        # A private chat shows the other person's avatar.
        ("private", "902", "https://q1.qlogo.cn/g?b=qq&nk=902&s=100"),
    ],
)
async def test_message_avatars_supply_platform_urls_and_bytes_to_host_cache(
    tmp_path, monkeypatch, kind, chat_id, chat_url
):
    requested: list[str] = []

    async def qlogo(url: str, **_kwargs) -> bytes:
        requested.append(url)
        return _picture()

    monkeypatch.setattr(accounts_avatar, "download_avatar", qlogo)
    avatars = FakeAvatars()

    refresh_message_avatars(avatars, _message(kind), requester=FakeHttp())
    await avatars.drain()

    assert sorted(requested) == sorted(
        [chat_url, "https://q1.qlogo.cn/g?b=qq&nk=902&s=100"]
    )
    assert avatars.images[("sender", "qq", "902")] == _picture()
    assert avatars.images[("chat", "qq", chat_id)] == _picture()
