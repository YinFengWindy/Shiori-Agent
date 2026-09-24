from __future__ import annotations

import logging

from agent.looping.interrupt import InterruptController
from agent.tools.message_push import MessagePushTool
from bootstrap.channel_host import ChannelHost
from bus.event_bus import EventBus
from bus.queue import MessageBus
from core.channels import ChannelHub
from core.common.channel_directory import ChannelDirectory
from core.net.http import SharedHttpResources
from infra.channels.base import AttachmentStore
from infra.channels.contract import Channel, ChannelContext
from session.manager import SessionManager

logger = logging.getLogger(__name__)


async def start_channels(
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
    previous_host: ChannelHost | None = None,
    channel_directory: ChannelDirectory | None = None,
) -> ChannelHost:
    """Constructs a traffic-free host, optionally reusing unchanged connections."""
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

    host = ChannelHost(_ctx_factory, transport_lock=bus.transport_lock)
    push_tool.set_transport_lock(bus.transport_lock)
    if not enable_message_channels:
        return host
    channel_hub = (
        ChannelHub.from_workspace(
            session_manager.workspace,
            session_manager=session_manager,
            channel_directory=channel_directory,
        )
        if getattr(session_manager, "workspace", None) is not None
        else None
    )
    for channel in plugin_channels or []:
        # Only independently owned plugin connections opt into reuse. Other
        # channels may retain resources owned by their plugin generation.
        # A channel that declares ``uses_bot_commands`` captures
        # ctx.bot_commands at start, so a changed command list must rebuild it
        # just like changed credentials; other channels ignore the list.
        key = getattr(channel, "configuration_key", None)
        configuration = (
            (key, tuple(bot_commands or []))
            if key is not None and getattr(channel, "uses_bot_commands", False)
            else key
        )
        existing = (
            previous_host.reusable(channel.name, configuration)
            if previous_host is not None and configuration is not None
            else None
        )
        if existing is not None:
            await channel.stop()
        host.add(existing or channel, configuration=configuration)

    return host
