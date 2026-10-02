from __future__ import annotations

import io
from unittest.mock import Mock

import pytest
from PIL import Image

import plugins.qq.backend.accounts_avatar as accounts_avatar
from agent.plugin_host.avatars import AvatarsCapability
from agent.plugin_host.effects import EffectScope
from core.channel_avatars import ChannelAvatarStore
from plugins.qq.backend.accounts_avatar import refresh_message_avatars
from plugins.qq.backend.accounts_inbound import inbound_message


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
async def test_message_avatars_are_fetched_from_qlogo_and_cached(
    tmp_path, monkeypatch, kind, chat_id, chat_url
):
    requested: list[str] = []

    async def qlogo(url: str, **_kwargs) -> bytes:
        requested.append(url)
        return _picture()

    monkeypatch.setattr(accounts_avatar, "download_avatar", qlogo)
    store = ChannelAvatarStore(tmp_path)
    avatars = AvatarsCapability(store, EffectScope("qq"), "qq")

    refresh_message_avatars(avatars, _message(kind), requester=Mock())
    for task in list(avatars._tasks):
        await task

    assert sorted(requested) == sorted(
        [chat_url, "https://q1.qlogo.cn/g?b=qq&nk=902&s=100"]
    )
    index = store.index()
    assert index.sender("qq", "902") is not None
    assert index.chat("qq", chat_id) is not None
