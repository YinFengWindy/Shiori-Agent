"""Explicitly granted setup services consumed by channel plugins."""

from typing import Protocol
from pathlib import Path

from shiori_sdk.accounts.capability import AccountsCapability
from shiori_sdk.extensions import ConfigValues
from shiori_sdk.rpc import RpcCapability
from shiori_sdk.runtime import PluginRuntimeContext
from shiori_sdk.storage import KeyValueStore
from shiori_sdk.processes import Processes
from shiori_sdk.http import HttpClient
from shiori_sdk.tools import ToolsCapability
from .avatars import AvatarsCapability
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


class ChannelPluginContext(PluginRuntimeContext, Protocol):
    """The statically checked setup boundary for channel and account plugins."""

    @property
    def manifest(self) -> ChannelDeclarations: ...
    @property
    def channels(self) -> ChannelsCapability: ...
    @property
    def accounts(self) -> AccountsCapability: ...
    @property
    def kv(self) -> KeyValueStore: ...
    @property
    def config(self) -> ConfigValues: ...
    @property
    def rpc(self) -> RpcCapability: ...
    @property
    def avatars(self) -> AvatarsCapability: ...
    @property
    def workspace(self) -> Path: ...
    @property
    def processes(self) -> Processes: ...
    @property
    def http(self) -> HttpClient: ...
    @property
    def tools(self) -> ToolsCapability: ...
