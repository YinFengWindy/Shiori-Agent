"""Telegram's public channel registration persists real host delivery receipts."""

import logging
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

from agent.tools.message_push import MessagePushTool
from bus.event_bus import EventBus
from shiori_sdk.messages import InboundMessage, OutboundMessage
from bus.queue import MessageBus
from core.channels import ChannelHub
from core.roles import RoleAggregateService, RoleStore
from core.net.http import SharedHttpResources
from infra.channels.base import AttachmentStore
from shiori_sdk.channels import ChannelContext
from infra.channels.intake import ChannelIntake
from plugins.telegram.backend.channel.lifecycle import TelegramChannel, Application
from session.manager import SessionManager


async def test_registered_telegram_sender_marks_the_committed_message(
    tmp_path, monkeypatch
):
    bot = SimpleNamespace(
        set_my_commands=AsyncMock(),
        send_message=AsyncMock(return_value=SimpleNamespace(message_id=99)),
    )
    app = SimpleNamespace(
        bot=bot,
        add_handler=Mock(),
        initialize=AsyncMock(),
        start=AsyncMock(),
        running=False,
        shutdown=AsyncMock(),
        updater=SimpleNamespace(running=False, start_polling=AsyncMock()),
    )
    builder = Mock()
    builder.token.return_value = builder
    builder.build.return_value = app
    monkeypatch.setattr(Application, "builder", lambda: builder)
    channel = TelegramChannel("123:token")
    sessions = SessionManager(tmp_path)
    roles = RoleStore(tmp_path)
    service = RoleAggregateService.from_runtime(
        workspace=tmp_path, role_store=roles, session_manager=sessions
    )
    service.create_role(role_id="mira", name="Mira", system_prompt="m")
    account = roles.accounts.register(
        plugin_id="telegram",
        platform="telegram",
        platform_account_id="123",
        config_ref="123",
        token="live",
        role_id="mira",
    )
    roles.accounts.report(account.record.id, "live", connection="online")
    hub = ChannelHub(service)
    inbound = hub.route_inbound(
        InboundMessage(
            "telegram", "u1", "123", "hello", metadata={"account_id": account.record.id}
        )
    )
    session = sessions.get_or_create(inbound.session_key)
    session.add_message(
        "assistant", "reply", thread_id=str(inbound.metadata["thread_id"])
    )
    sessions.save(session)
    message_id = str(session.messages[-1]["id"])
    http = SharedHttpResources()
    bus = MessageBus()
    ctx = ChannelContext(
        bus=bus,
        session_manager=sessions,
        event_bus=EventBus(),
        push_tool=MessagePushTool(),
        attachment_store=AttachmentStore(tmp_path / "uploads"),
        http_resources=http,
        interrupt_controller=None,
        bot_commands=[],
        log=logging.getLogger(__name__),
        intake_factory=ChannelIntake,
        channel_hub=hub,
    )
    try:
        await channel.start(ctx)
        await bus._dispatch_message(
            OutboundMessage(
                "telegram",
                "123",
                "reply",
                metadata=dict(inbound.metadata),
                committed_message_id=message_id,
            )
        )
        delivered = sessions._store.get_message(message_id)
        assert delivered is not None
        assert (delivered["delivery_status"], delivered["external_message_id"]) == (
            "sent",
            "99",
        )
    finally:
        await channel.stop()
        await http.aclose()
