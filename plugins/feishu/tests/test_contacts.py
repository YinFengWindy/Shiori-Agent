"""Senders' names and avatars from the Feishu contact directory."""

from __future__ import annotations

import io
from pathlib import Path

import httpx
import pytest
from shiori_sdk.testing.avatars import FakeAvatars
from PIL import Image

from shiori_sdk.testing.storage import FakeKV
from shiori_sdk.messages import InboundMessage
from plugins.feishu.backend.api import FeishuApi
from plugins.feishu.backend.contacts import FeishuContacts

OPEN_ID = "ou_user"
CHAT_ID = "oc_chat"
CHANNEL = "feishu:cli_a"


def _png() -> bytes:
    output = io.BytesIO()
    Image.new("RGB", (8, 8), "pink").save(output, format="PNG")
    return output.getvalue()


def _contacts(tmp_path: Path, *, permitted: bool, lookups: list[str]):
    """Contacts over a fake Feishu that records every contact lookup."""

    async def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/tenant_access_token/internal"):
            return httpx.Response(
                200, json={"code": 0, "tenant_access_token": "t", "expire": 7200}
            )
        if request.url.host == "cdn.test":
            return httpx.Response(200, content=_png())
        lookups.append(request.url.path)
        if not permitted:
            return httpx.Response(400, json={"code": 99991672, "msg": "no scope"})
        user = {"name": "小王", "avatar": {"avatar_240": "https://cdn.test/u.png"}}
        return httpx.Response(200, json={"code": 0, "data": {"user": user}})

    api = FeishuApi(
        "cli_a",
        "secret",
        "https://open.feishu.cn",
        transport=httpx.MockTransport(handler),
    )
    api.open()
    avatars = FakeAvatars()
    contacts = FeishuContacts(
        api,
        store=FakeKV(),
        ref="feishu:cli_a",
        avatars=avatars,
    )
    return api, contacts, avatars, avatars


def _message() -> InboundMessage:
    return InboundMessage(
        channel=CHANNEL, sender=OPEN_ID, chat_id=CHAT_ID, content="你好"
    )


async def test_one_lookup_names_the_sender_and_caches_both_avatars(tmp_path):
    lookups: list[str] = []
    api, contacts, avatars, store = _contacts(tmp_path, permitted=True, lookups=lookups)

    contacts.refresh(_message())
    await avatars.drain()
    await api.aclose()

    assert lookups == [f"/open-apis/contact/v3/users/{OPEN_ID}"]
    assert contacts.name(OPEN_ID) == "小王"
    assert store.images[("sender", CHANNEL, OPEN_ID)] == _png()
    # A private chat shows the other person's avatar.
    assert store.images[("chat", CHANNEL, CHAT_ID)] == _png()


async def test_without_the_contact_permission_there_is_no_name_or_avatar(
    tmp_path, caplog: pytest.LogCaptureFixture
):
    lookups: list[str] = []
    api, contacts, avatars, store = _contacts(
        tmp_path, permitted=False, lookups=lookups
    )

    contacts.refresh(_message())
    with pytest.raises(ExceptionGroup):
        await avatars.drain()
    await api.aclose()

    assert len(lookups) == 1
    assert contacts.name(OPEN_ID) is None
    assert ("sender", CHANNEL, OPEN_ID) not in store.images
