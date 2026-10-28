"""Explicitly granted setup services consumed by channel plugins."""

from typing import Protocol

from . import Channel
from .chat_types import ChatTypeDeclaration
from .group import AccountChannelGroup


class ChannelDeclarations(Protocol):
    """Read validated public channel declarations without exposing manifest internals."""

    def channel_chat_types(self, name: str) -> tuple[ChatTypeDeclaration, ...]: ...


class ChannelsCapability(Protocol):
    """Contribute declared transports to the host lifecycle."""

    def add(self, channel: Channel) -> None: ...
    def group(self, name: str) -> AccountChannelGroup:
        """Construct a host-owned group; add it through the same declaration gate."""
        ...
