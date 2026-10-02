"""Bootstrap passes the selected workspace's attachment storage to Telegram."""

import asyncio
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

from telegram import Chat, Message, PhotoSize, Update, User
from telegram.ext import Application, BaseHandler

from agent.plugin_host.capabilities import AccountsCapability
from agent.plugin_host.effects import EffectScope
from agent.tools.message_push import MessagePushTool
from bootstrap.channels import start_channels
from bus.event_bus import EventBus
from bus.queue import MessageBus
from core.net.http import SharedHttpResources
from core.roles import RoleStore
from plugins.telegram.backend.channel.lifecycle import TelegramChannel
from session.manager import SessionManager


async def test_telegram_download_uses_bootstrapped_workspace(tmp_path, monkeypatch):
    selected = tmp_path / "selected"
    default = tmp_path / "default"
    monkeypatch.setattr(
        "infra.channels.base.resolve_default_workspace", lambda: default
    )
    roles = RoleStore(selected)
    roles.create_role(role_id="mira", name="Mira", system_prompt="m")
    roles.accounts.publish_generation("g1")
    effects = EffectScope("telegram")
    accounts = AccountsCapability(roles.accounts, effects, "telegram", "g1")

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
        "123:token", config_ref="123", accounts=accounts, role_id="mira"
    )
    bus = MessageBus()
    http = SharedHttpResources()
    host = await start_channels(
        bus=bus,
        session_manager=SessionManager(selected),
        push_tool=MessagePushTool(),
        http_resources=http,
        event_bus=EventBus(),
        plugin_channels=[channel],
        role_store=roles,
    )
    try:
        await host.start_all()
        assert host.failures == []
        app.updater.start_polling.assert_awaited_once()
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
        inbound = await asyncio.wait_for(bus.consume_inbound(), 1)
        [path] = [Path(value) for value in inbound.media]
        assert path.read_bytes() == b"telegram photo"
        assert path.parent == selected / "uploads"
        assert not (default / "uploads").exists()
    finally:
        await host.stop_all()
        assert await effects.dispose_all() == []
        await http.aclose()
