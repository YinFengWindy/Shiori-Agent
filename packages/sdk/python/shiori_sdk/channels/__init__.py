"""Public channel composition contracts."""

import logging
from dataclasses import dataclass
from typing import NotRequired, Protocol, TypedDict, runtime_checkable

from shiori_sdk.http import HttpResources
from shiori_sdk.runtime import EventsCapability
from .hooks import (
    SupportsDefaultChatType,
    SupportsStreamEvents,
    SupportsSystemPromptHint,
)
from .services import (
    AttachmentStore,
    ChannelHub,
    ChannelSessions,
    IntakeFactory,
    InterruptController,
    MessageBus,
    PushSenders,
)


class Channel(Protocol):
    """A connection whose inbound admission stops independently from accepted replies."""

    name: str

    async def start(self, ctx: "ChannelContext") -> None: ...
    async def stop(self) -> None: ...
    def pause_intake(self) -> None: ...
    def resume_intake(self) -> None: ...


@runtime_checkable
class SupportsBotCommands(Protocol):
    """Include contributed commands in a channel's cross-generation reuse key."""

    uses_bot_commands: bool


class ChannelStatus(TypedDict):
    """Transport health reported without host interpretation."""

    connected: bool
    account: NotRequired[str]
    detail: NotRequired[str]


@runtime_checkable
class SupportsChannelStatus(Protocol):
    """Optional live connection status for presentation."""

    def status(self) -> ChannelStatus: ...


@dataclass
class ChannelContext:
    """Runtime-selected services, shared while each connection retains its own intake."""

    bus: MessageBus
    session_manager: ChannelSessions
    event_bus: EventsCapability
    push_tool: PushSenders
    attachment_store: AttachmentStore
    http_resources: HttpResources
    interrupt_controller: InterruptController | None
    bot_commands: list[tuple[str, str]]
    log: logging.Logger
    intake_factory: IntakeFactory
    channel_hub: ChannelHub | None = None
    intake_paused: bool = False
