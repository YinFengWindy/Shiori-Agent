from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import TYPE_CHECKING, NotRequired, Protocol, TypedDict, runtime_checkable

from agent.looping.interrupt import InterruptController
from agent.tools.message_push import MessagePushTool
from bus.event_bus import EventBus
from bus.queue import MessageBus
from core.common.channel_directory import (
    SupportsDefaultChatType,
    SupportsStreamEvents,
    SupportsSystemPromptHint,
)
from core.net.http import SharedHttpResources
from infra.channels.base import AttachmentStore
from session.manager import SessionManager

if TYPE_CHECKING:
    from core.channels import ChannelHub


__all__ = [
    "Channel",
    "ChannelContext",
    "ChannelStatus",
    "SupportsBotCommands",
    "SupportsChannelStatus",
    "SupportsDefaultChatType",
    "SupportsStreamEvents",
    "SupportsSystemPromptHint",
]


class Channel(Protocol):
    """A transport whose inbound admission can stop independently of outbound work.

    Optional hooks replace channel-name checks in the core; a channel implements
    only those it needs: ``status()`` (:class:`SupportsChannelStatus`),
    ``supports_stream_events(chat_id)`` (:class:`SupportsStreamEvents`),
    ``system_prompt_hint(chat_id)`` (:class:`SupportsSystemPromptHint`), the
    ``default_chat_type`` attribute (:class:`SupportsDefaultChatType`) and the
    ``uses_bot_commands`` attribute (:class:`SupportsBotCommands`).
    """

    name: str

    async def start(self, ctx: ChannelContext) -> None: ...
    async def stop(self) -> None: ...
    def pause_intake(self) -> None: ...
    def resume_intake(self) -> None: ...


@runtime_checkable
class SupportsBotCommands(Protocol):
    """Declares that the channel consumes ``ChannelContext.bot_commands`` at start.

    Only such channels fold the command list into their cross-generation reuse
    key, so a changed command list rebuilds them; channels without the
    attribute (default ``False``) keep their connection across command changes.
    """

    uses_bot_commands: bool


class ChannelStatus(TypedDict):
    """Transport health reported by a channel; the host adds no interpretation."""

    connected: bool
    account: NotRequired[str]
    detail: NotRequired[str]


@runtime_checkable
class SupportsChannelStatus(Protocol):
    """Optional ``Channel`` extension exposing live connection status to the desktop."""

    def status(self) -> ChannelStatus: ...


@dataclass
class ChannelContext:
    bus: MessageBus
    session_manager: SessionManager
    event_bus: EventBus
    push_tool: MessagePushTool
    attachment_store: AttachmentStore
    http_resources: SharedHttpResources
    interrupt_controller: InterruptController | None
    bot_commands: list[tuple[str, str]]
    log: logging.Logger
    channel_hub: "ChannelHub | None" = None
    intake_paused: bool = False
