from __future__ import annotations

import logging

from agent.config_models import Config
from agent.looping.interrupt import InterruptController
from agent.tools.message_push import MessagePushTool
from bootstrap.channel_host import ChannelHost
from bus.event_bus import EventBus
from bus.queue import MessageBus
from core.channels import ChannelHub
from core.net.http import SharedHttpResources
from infra.channels.base import AttachmentStore
from infra.channels.contract import Channel, ChannelContext
from session.manager import SessionManager

logger = logging.getLogger(__name__)


async def start_channels(
    config: Config,
    *,
    bus: MessageBus,
    session_manager: SessionManager,
    push_tool: MessagePushTool,
    http_resources: SharedHttpResources,
    event_bus: EventBus,
    bot_commands: list[tuple[str, str]] | None = None,
    interrupt_controller: InterruptController | None = None,
    plugin_channels: list[Channel] | None = None,
    enable_message_channels: bool = True,
) -> tuple[object | None, ChannelHost]:
    attachment_store = AttachmentStore()
    channel_hub: ChannelHub | None = None

    def _ctx_factory(channel: Channel) -> ChannelContext:
        return ChannelContext(
            bus=bus,
            session_manager=session_manager,
            event_bus=event_bus,
            push_tool=push_tool,
            attachment_store=attachment_store,
            http_resources=http_resources,
            interrupt_controller=interrupt_controller,
            bot_commands=bot_commands or [],
            log=logging.getLogger(f"channels.{channel.name}"),
            channel_hub=channel_hub,
        )

    host = ChannelHost(_ctx_factory)
    if not enable_message_channels:
        return None, host
    channel_hub = (
        ChannelHub.from_workspace(
            session_manager.workspace,
            session_manager=session_manager,
        )
        if getattr(session_manager, "workspace", None) is not None
        else None
    )
    if config.channels.telegram and config.channels.telegram.token:
        tg = config.channels.telegram
        try:
            from infra.channels.telegram_channel import TelegramChannel

            host.add(TelegramChannel(
                token=tg.token,
                bus=bus,
                session_manager=session_manager,
                bot_commands=bot_commands,
                event_bus=event_bus,
                interrupt_controller=interrupt_controller,
                channel_name=tg.channel_name,
                channel_hub=channel_hub,
            ))
        except Exception as exc:
            logger.warning("跳过 Telegram 渠道: %s", exc)

    if config.channels.qq and config.channels.qq.bot_uin:
        qq = config.channels.qq
        try:
            from infra.channels.qq_channel import QQChannel

            host.add(QQChannel(
                bot_uin=qq.bot_uin,
                bus=bus,
                session_manager=session_manager,
                websocket_open_timeout_seconds=qq.websocket_open_timeout_seconds,
                http_requester=http_resources.external_default,
                event_bus=event_bus,
                interrupt_controller=interrupt_controller,
                channel_hub=channel_hub,
            ))
        except Exception as exc:
            logger.warning("跳过 QQ 渠道: %s", exc)

    for channel in plugin_channels or []:
        host.add(channel)

    return None, host
