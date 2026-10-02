"""Senders' names and avatars from the Feishu contact directory."""

from __future__ import annotations

import io
import logging
from pathlib import Path

import httpx
import pytest
from PIL import Image

from agent.plugin_host.avatars import AvatarsCapability
from agent.plugin_host.effects import EffectScope
from agent.plugin_host.kv import PluginKVStore
from bus.events import InboundMessage
from core.channel_avatars import ChannelAvatarStore
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
    store = ChannelAvatarStore(tmp_path)
    avatars = AvatarsCapability(store, EffectScope("feishu"), "feishu")
    contacts = FeishuContacts(
        api,
        store=PluginKVStore(tmp_path / "kv.json"),
        ref="feishu:cli_a",
        avatars=avatars,
    )
    return api, contacts, avatars, store


def _message() -> InboundMessage:
    return InboundMessage(
        channel=CHANNEL, sender=OPEN_ID, chat_id=CHAT_ID, content="你好"
    )


async def test_one_lookup_names_the_sender_and_caches_both_avatars(tmp_path):
    lookups: list[str] = []
    api, contacts, avatars, store = _contacts(tmp_path, permitted=True, lookups=lookups)

    contacts.refresh(_message())
    for task in list(avatars._tasks):
        await task
    await api.aclose()

    assert lookups == [f"/open-apis/contact/v3/users/{OPEN_ID}"]
    assert contacts.name(OPEN_ID) == "小王"
    index = store.index()
    assert index.sender(CHANNEL, OPEN_ID) is not None
    # A private chat shows the other person's avatar.
    assert index.chat(CHANNEL, CHAT_ID) is not None


async def test_without_the_contact_permission_there_is_no_name_or_avatar(
    tmp_path, caplog: pytest.LogCaptureFixture
):
    lookups: list[str] = []
    api, contacts, avatars, store = _contacts(
        tmp_path, permitted=False, lookups=lookups
    )

    with caplog.at_level(logging.WARNING):
        contacts.refresh(_message())
        for task in list(avatars._tasks):
            await task
    await api.aclose()

    assert len(lookups) == 1
    assert "头像获取失败" in caplog.text
    assert contacts.name(OPEN_ID) is None
    assert store.index().sender(CHANNEL, OPEN_ID) is None
