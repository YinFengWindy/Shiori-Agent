"""Sender and chat photos fetched from the Bot API into the host's avatar cache."""

from __future__ import annotations

import io
from types import SimpleNamespace
from typing import Any, cast
from unittest.mock import AsyncMock

import pytest
from PIL import Image

from shiori_sdk.testing.avatars import FakeAvatars
from shiori_sdk.messages import InboundMessage
from plugins.telegram.backend.channel.avatar import refresh_message_avatars


def _png() -> bytes:
    output = io.BytesIO()
    Image.new("RGB", (8, 8), "pink").save(output, format="PNG")
    return output.getvalue()


class _FakeBot:
    """Answers the Bot API calls behind profile and chat photos."""

    def __init__(self) -> None:
        self.calls: list[tuple[str, object]] = []

    async def get_user_profile_photos(self, user_id: int, *, limit: int):
        self.calls.append(("get_user_profile_photos", user_id))
        sizes = [
            SimpleNamespace(file_id="user-small", width=64),
            SimpleNamespace(file_id="user-160", width=160),
        ]
        return SimpleNamespace(photos=[sizes])

    async def get_chat(self, chat_id: str):
        self.calls.append(("get_chat", chat_id))
        return SimpleNamespace(photo=SimpleNamespace(small_file_id=f"photo:{chat_id}"))

    async def get_file(self, file_id: str):
        self.calls.append(("get_file", file_id))
        return SimpleNamespace(download_as_bytearray=AsyncMock(return_value=_png()))


def _message(sender: str) -> InboundMessage:
    return InboundMessage(
        channel="telegram_bot",
        sender=sender,
        chat_id="-1001",
        content="hello",
        metadata={"chat_type": "supergroup"},
    )


async def _refreshed(tmp_path, bot: _FakeBot, sender: str) -> FakeAvatars:
    avatars = FakeAvatars()
    refresh_message_avatars(avatars, cast(Any, bot), _message(sender))
    await avatars.drain()
    return avatars


@pytest.mark.asyncio
async def test_sender_profile_photo_and_group_photo_are_cached(tmp_path):
    bot = _FakeBot()

    store = await _refreshed(tmp_path, bot, "77")

    assert ("get_user_profile_photos", 77) in bot.calls
    # The first size at least 128px wide, and the chat's small photo.
    assert {call for call in bot.calls if call[0] == "get_file"} == {
        ("get_file", "user-160"),
        ("get_file", "photo:-1001"),
    }
    assert store.images[("sender", "telegram_bot", "77")] == _png()
    assert store.images[("chat", "telegram_bot", "-1001")] == _png()


@pytest.mark.asyncio
async def test_anonymous_sender_chat_uses_that_chats_photo(tmp_path):
    bot = _FakeBot()

    store = await _refreshed(tmp_path, bot, "chat:-1009")

    assert ("get_chat", "-1009") in bot.calls
    assert not any(call[0] == "get_user_profile_photos" for call in bot.calls)
    assert store.images[("sender", "telegram_bot", "chat:-1009")] == _png()
