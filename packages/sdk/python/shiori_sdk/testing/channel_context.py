"""Compose SDK-only channel plugin setup with public manifest declarations."""

import logging
from collections.abc import Callable, Sequence
from pathlib import Path
import yaml

from shiori_sdk.channels import Channel, ChannelContext
from shiori_sdk.channels.services import (
    ChannelHub,
    ChannelSessions,
    IntakeFactory,
    InterruptController,
    MessageBus,
)
from shiori_sdk.http import HttpResources
from shiori_sdk.runtime import EventsCapability
from shiori_sdk.core.services import (
    ACCOUNTS,
    AVATARS,
    CHANNELS,
    CONFIG,
    HTTP,
    KV,
    PROCESSES,
    RPC,
    TOOLS,
    WORKSPACE,
)
from shiori_sdk.channels.chat_types import ChatTypeDeclaration, parse_chat_type
from .accounts import FakeAccounts
from .extensions import FakeConfig
from .context import FakePluginContext
from .storage import FakeKV
from .memory_context import FakeRpc
from .processes import FakeProcesses
from .http import FakeHttp
from .avatars import FakeAvatars
from .channel_group import FakeAccountChannelGroup
from .channel_hub import FakeChannelHub
from .channel_intake import FakeChannelIntake
from .channel_services import FakeAttachmentStore, FakeMessageBus
from .channel_sessions import FakeChannelSessions
from .events import FakeEvents
from .tools import FakeTools
from .http import FakeHttpResources


class FakeChannelDeclarations:
    """Read plugin-owned declarations for tests; host manifest validation remains separate."""

    def __init__(self, path: Path):
        loaded = yaml.safe_load((path / "manifest.yaml").read_text(encoding="utf-8"))
        if not isinstance(loaded, dict):
            raise ValueError(f"manifest.yaml 格式错误，期望 dict: {path}")
        contributes = loaded.get("contributes")
        channels: object = []
        if isinstance(contributes, dict):
            listed = contributes.get("channels", [])
            if isinstance(listed, list):
                channels = listed
        self.values = {**loaded, "channels": channels}

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


class FakeChannelSetupContext(FakePluginContext):
    """A setup context stocked for a channel plugin; no host storage or runtime.

    Each fake sits on ``fake_<key name>`` and is served under that key, so a
    plugin's ``ctx.require(RPC)`` returns ``fake_rpc``. Only keys the package
    manifest declares in ``inject`` / ``optional_inject`` resolve.
    """

    def __init__(
        self,
        plugin_id: str,
        plugin_dir: Path,
        *,
        account_ids: Callable[[str], str] | None = None,
        kv: FakeKV | None = None,
        workspace: Path | None = None,
    ):
        """``account_ids`` maps a platform account ID to the host account ID.

        Pass an earlier context's ``fake_kv`` as ``kv`` to model a restart over
        saved plugin data. ``workspace`` defaults to ``plugin_dir``.
        """
        super().__init__(plugin_id, plugin_dir, package_dir=plugin_dir)
        self.manifest = FakeChannelDeclarations(plugin_dir)
        self.fake_channels = FakeChannels()
        self.fake_accounts = FakeAccounts(plugin_id, id_factory=account_ids)
        self.fake_kv = kv if kv is not None else FakeKV()
        self.fake_config = FakeConfig()
        self.fake_rpc = FakeRpc()
        self.fake_processes = FakeProcesses()
        self.fake_http = FakeHttp()
        self.fake_avatars = FakeAvatars()
        self.fake_tools = FakeTools()
        self.serve(CHANNELS, self.fake_channels)
        self.serve(ACCOUNTS, self.fake_accounts)
        self.serve(KV, self.fake_kv)
        self.serve(CONFIG, self.fake_config)
        self.serve(RPC, self.fake_rpc)
        self.serve(WORKSPACE, workspace if workspace is not None else plugin_dir)
        self.serve(PROCESSES, self.fake_processes)
        self.serve(HTTP, self.fake_http)
        self.serve(AVATARS, self.fake_avatars)
        self.serve(TOOLS, self.fake_tools)

    async def aclose(self) -> None:
        """Dispose setup registrations and cancel pending avatar downloads."""
        try:
            await super().aclose()
        finally:
            self.fake_tools.tools.clear()
            await self.fake_avatars.aclose()


def fake_channel_context(
    upload_dir: Path,
    *,
    bus: MessageBus | None = None,
    session_manager: ChannelSessions | None = None,
    event_bus: EventsCapability | None = None,
    http_resources: HttpResources | None = None,
    interrupt_controller: InterruptController | None = None,
    bot_commands: Sequence[tuple[str, str]] = (),
    channel_hub: ChannelHub | None = None,
    intake_factory: IntakeFactory = FakeChannelIntake,
    intake_paused: bool = False,
) -> ChannelContext:
    """Build the start context a host passes to ``Channel.start`` from SDK fakes.

    Every omitted service is a fresh SDK fake (``FakeMessageBus``,
    ``FakeChannelSessions``, ``FakeEvents``, ``FakeHttpResources``,
    ``FakeChannelHub``); pass your own instance to
    inspect it. Received attachments are written beneath ``upload_dir``.
    """
    return ChannelContext(
        bus=bus if bus is not None else FakeMessageBus(),
        session_manager=(
            session_manager if session_manager is not None else FakeChannelSessions()
        ),
        event_bus=event_bus if event_bus is not None else FakeEvents(),
        attachment_store=FakeAttachmentStore(upload_dir),
        http_resources=(
            http_resources if http_resources is not None else FakeHttpResources()
        ),
        interrupt_controller=interrupt_controller,
        bot_commands=list(bot_commands),
        log=logging.getLogger("shiori_sdk.testing.channel"),
        intake_factory=intake_factory,
        channel_hub=channel_hub if channel_hub is not None else FakeChannelHub(),
        intake_paused=intake_paused,
    )
