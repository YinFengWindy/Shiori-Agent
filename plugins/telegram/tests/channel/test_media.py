"""Received pictures are downloaded into the attachment storage the host provides."""

from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest
from telegram import Chat, Message, PhotoSize, Update, User
from telegram.ext import Application, BaseHandler

from plugins.telegram.backend.channel.lifecycle import TelegramChannel
from shiori_sdk.testing.accounts import FakeAccounts
from shiori_sdk.testing.channel_context import fake_channel_context
from shiori_sdk.testing.channel_services import FakeMessageBus


@pytest.mark.asyncio
async def test_photo_is_downloaded_into_the_host_attachment_storage(
    tmp_path, monkeypatch
):
    async def download(path: Path) -> Path:
        path.write_bytes(b"telegram photo")
        return path

    bot = SimpleNamespace(
        get_me=AsyncMock(return_value=User(123, "Bot", True, username="test_bot")),
        get_user_profile_photos=AsyncMock(return_value=SimpleNamespace(photos=())),
        set_my_commands=AsyncMock(),
        send_chat_action=AsyncMock(),
        get_file=AsyncMock(
            return_value=SimpleNamespace(
                download_to_drive=AsyncMock(side_effect=download)
            )
        ),
    )
    handlers: list[BaseHandler] = []
    app = SimpleNamespace(
        bot=bot,
        add_handler=handlers.append,
        initialize=AsyncMock(),
        start=AsyncMock(),
        running=False,
        shutdown=AsyncMock(),
        updater=SimpleNamespace(running=False, start_polling=AsyncMock()),
    )
    builder = Mock()
    builder.bot.return_value = builder
    builder.build.return_value = app
    monkeypatch.setattr(Application, "builder", lambda: builder)
    channel = TelegramChannel(
        "123:token", config_ref="123", accounts=FakeAccounts("telegram"), role_id="mira"
    )
    bus = FakeMessageBus()
    uploads = tmp_path / "uploads"
    await channel.start(fake_channel_context(uploads, bus=bus))
    try:
        update = Update(
            update_id=1,
            message=Message(
                message_id=1,
                date=datetime.now(timezone.utc),
                chat=Chat(456, "private"),
                from_user=User(456, "Sender", False),
                photo=[PhotoSize("photo-1", "unique-1", 100, 100)],
                caption="Look at this",
            ),
        )
        # Dispatch through the handler registered with Telegram's application.
        handler = next(handler for handler in handlers if handler.check_update(update))
        await handler.callback(update, SimpleNamespace(bot=bot))
        await channel._intake.drain()

        [inbound] = bus.inbound
        assert inbound.content == "Look at this"
        bot.get_file.assert_awaited_once_with("photo-1")
        [path] = [Path(value) for value in inbound.media]
        assert path.read_bytes() == b"telegram photo"
        assert path.parent == uploads
    finally:
        await channel.stop()
