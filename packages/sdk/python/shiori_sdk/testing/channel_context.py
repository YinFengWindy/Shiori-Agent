"""Compose SDK-only channel plugin setup with public manifest declarations."""

from pathlib import Path
import yaml

from shiori_sdk.channels import Channel
from shiori_sdk.channels.chat_types import ChatTypeDeclaration, parse_chat_type
from shiori_sdk.channels.context import ChannelPluginContext
from .accounts import FakeAccounts
from .extensions import FakeConfig
from .context import FakePluginContext
from .storage import FakeKV
from .memory_context import FakeRpc
from .processes import FakeProcesses
from .http import FakeHttp
from .avatars import FakeAvatars
from .channel_group import FakeAccountChannelGroup


class FakeChannelDeclarations:
    """Read plugin-owned declarations for tests; host manifest validation remains separate."""

    def __init__(self, path: Path):
        self.values = yaml.safe_load(
            (path / "manifest.yaml").read_text(encoding="utf-8")
        )

    def channel_chat_types(self, name: str) -> tuple[ChatTypeDeclaration, ...]:
        """Return the public declarations that the real setup function consumes."""
        channel = next(
            item for item in self.values.get("channels", []) if item["name"] == name
        )
        return tuple(
            ChatTypeDeclaration(
                type=parse_chat_type(item["type"], "type"),
                label=item["label"],
                chat_id_label=item["chat_id_label"],
                chat_id_hint=item.get("chat_id_hint"),
                prefix=item.get("prefix"),
            )
            for item in channel.get("chat_types", [])
        )


class FakeChannels:
    """Record lifecycle contributions without starting platform connections."""

    def __init__(self):
        self.channels: list[Channel] = []

    def add(self, channel: Channel) -> None:
        """Retain the plugin's contributed transport for explicit test driving."""
        self.channels.append(channel)

    def group(self, name: str) -> FakeAccountChannelGroup:
        """Construct a test-owned collection without host coordination."""
        return FakeAccountChannelGroup(name)


class FakeChannelPluginContext(FakePluginContext):
    """Channel setup services using no host storage, runtime or manifest loader."""

    def __init__(self, plugin_id: str, plugin_dir: Path):
        super().__init__(plugin_id, plugin_dir)
        self.manifest = FakeChannelDeclarations(plugin_dir)
        self.channels = FakeChannels()
        self.accounts = FakeAccounts(plugin_id)
        self.kv = FakeKV()
        self.config = FakeConfig()
        self.rpc = FakeRpc()
        self.workspace = plugin_dir
        self.processes = FakeProcesses()
        self.http = FakeHttp()
        self.avatars = FakeAvatars()

    def as_capability(self) -> ChannelPluginContext:
        """Check this composition at the same setup boundary as the host."""
        return self

    async def aclose(self) -> None:
        """Dispose setup registrations and cancel pending avatar downloads."""
        try:
            await super().aclose()
        finally:
            await self.avatars.aclose()
