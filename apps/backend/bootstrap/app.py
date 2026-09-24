from __future__ import annotations

import asyncio
import logging
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

from agent.config_models import Config
from bootstrap.channel_host import ChannelHost
from bootstrap.channels import start_channels
from bootstrap.tools import CoreRuntime, build_core_runtime
from bootstrap.runtime.dispatcher import RuntimeDispatcher
from bootstrap.runtime.events import RuntimeEventBus
from bootstrap.runtime.generations import GenerationManager, RuntimeCandidate
from bootstrap.runtime.reload import RuntimeReloadMixin
from bootstrap.runtime.background import RuntimeBackgroundMixin
from bootstrap.runtime.shutdown import RuntimeShutdownMixin
from bootstrap.runtime.construction import prepare_core_runtime
from bus.event_bus import EventBus
from core.common.workspace import resolve_default_workspace
from core.roles import (
    LonelinessHeartbeatLoop,
)
from core.net.http import (
    SharedHttpResources,
    configure_default_shared_http_resources,
)

if TYPE_CHECKING:
    from agent.looping.core import AgentLoop
    from agent.mcp.registry import McpServerRegistry
    from agent.provider import LLMProvider
    from agent.scheduler import SchedulerService
    from agent.tools.message_push import MessagePushTool
    from agent.tools.registry import ToolRegistry
    from bus.queue import MessageBus
    from core.memory.runtime import MemoryRuntime
    from core.roles import RoleRelationshipRuntimeService
    from proactive_v2.presence import PresenceStore
    from session.manager import SessionManager


def configure_logging_stream(stream) -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s  %(levelname)-8s  %(name)s  %(message)s",
        datefmt="%H:%M:%S",
        stream=stream,
        force=True,
    )
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("telegram").setLevel(logging.WARNING)
    logging.getLogger("apscheduler").setLevel(logging.WARNING)
    logging.getLogger("openai").setLevel(logging.WARNING)


configure_logging_stream(sys.stderr)

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class RuntimeFeatures:
    enable_message_channels: bool = True
    enable_proactive: bool = True


SERVICE_RUNTIME_FEATURES = RuntimeFeatures()
DESKTOP_RUNTIME_FEATURES = RuntimeFeatures(
    enable_message_channels=True,
)


class AppRuntime(RuntimeReloadMixin, RuntimeBackgroundMixin, RuntimeShutdownMixin):
    def __init__(
        self,
        config: Config,
        workspace: Path,
        *,
        features: RuntimeFeatures = SERVICE_RUNTIME_FEATURES,
    ) -> None:
        self.config = config
        self.workspace = workspace
        self.features = features
        self.http_resources = SharedHttpResources()
        self.channel_host: ChannelHost | None = None
        self.core: CoreRuntime | None = None
        self.event_bus: EventBus | None = None
        self.proactive_loops = {}
        self._background_tasks: list[asyncio.Task[None]] = []
        self._memory_optimizer = None
        self._shutdown = False
        self._started = False
        self._dispatcher = RuntimeDispatcher(self)
        self._background_groups = {}
        self._cleanup_errors: list[Exception] = []
        self._generation_manager = GenerationManager()
        self._generation_manager.on_closed = self._generation_closed

    # The published generation owns these capabilities; tasks that must keep
    # their starting configuration should read them through a pinned lease
    # instead of this always-current view.

    @property
    def agent_loop(self) -> AgentLoop | None:
        return self.core.loop if self.core is not None else None

    @property
    def bus(self) -> MessageBus | None:
        return self.core.bus if self.core is not None else None

    @property
    def tools(self) -> ToolRegistry | None:
        return self.core.tools if self.core is not None else None

    @property
    def push_tool(self) -> MessagePushTool | None:
        return self.core.push_tool if self.core is not None else None

    @property
    def session_manager(self) -> SessionManager | None:
        return self.core.session_manager if self.core is not None else None

    @property
    def scheduler(self) -> SchedulerService | None:
        return self.core.scheduler if self.core is not None else None

    @property
    def provider(self) -> LLMProvider | None:
        return self.core.provider if self.core is not None else None

    @property
    def light_provider(self) -> LLMProvider | None:
        return self.core.light_provider if self.core is not None else None

    @property
    def mcp_registry(self) -> McpServerRegistry | None:
        return self.core.mcp_registry if self.core is not None else None

    @property
    def memory_runtime(self) -> MemoryRuntime | None:
        return self.core.memory_runtime if self.core is not None else None

    @property
    def presence(self) -> PresenceStore | None:
        return self.core.presence if self.core is not None else None

    @property
    def relationship_runtime(self) -> RoleRelationshipRuntimeService | None:
        return self.core.relationship_runtime if self.core is not None else None

    async def start(self) -> None:
        if self._started:
            return
        configure_default_shared_http_resources(self.http_resources)
        try:
            self.event_bus = EventBus()
            self.core = await prepare_core_runtime(
                self.config,
                self.workspace,
                self.http_resources,
                builder=build_core_runtime,
                event_bus=RuntimeEventBus(self.event_bus),
                event_outlet=self.event_bus,
                agent_loop_provider=lambda: self._dispatcher,
            )
            event_bus = self.event_bus
            await self.core.start()
            current = RuntimeCandidate(1, self.core, self.config, published=True)
            self._generation_manager.start(current)
            self.bus.bind_runtime_admission(self.acquire)

            plugin_manager = getattr(self.core, "plugin_manager", None)
            self.channel_host = await start_channels(
                self.config,
                bus=self.core.bus,
                session_manager=self.core.session_manager,
                push_tool=self.core.push_tool,
                http_resources=self.http_resources,
                event_bus=event_bus,
                bot_commands=plugin_manager.bot_commands if plugin_manager else None,
                interrupt_controller=self._dispatcher,
                plugin_channels=plugin_manager.channels if plugin_manager else None,
                enable_message_channels=self.features.enable_message_channels,
                channel_directory=self.core.channel_directory,
            )
            current.channel_names = frozenset(
                channel.name for channel in self.channel_host.channels
            )
            # The long-lived host keeps the published connections across handovers.
            self.core.channel_directory.bind(self.channel_host.get)
            await self.channel_host.start_all()

            self._background_tasks = [
                asyncio.create_task(self._dispatcher.run(), name="agent_loop"),
                asyncio.create_task(
                    self.bus.dispatch_outbound(),
                    name="bus_dispatch_outbound",
                ),
                asyncio.create_task(self.scheduler.run(), name="scheduler"),
            ]
            self._prepare_background(current)
            self._publish_background(None, current)
            if self.relationship_runtime is not None:
                loneliness_loop = LonelinessHeartbeatLoop(
                    self.relationship_runtime,
                    role_store=self.core.relationship_runtime.role_store,
                )
                self._background_tasks.extend(
                    [
                        asyncio.create_task(
                            loneliness_loop.run(),
                            name="loneliness_heartbeat_loop",
                        ),
                    ]
                )
            self._started = True
        except BaseException:
            await self.shutdown()
            raise

    async def run(self) -> None:
        try:
            await self.start()
            if self._background_tasks:
                await asyncio.gather(*self._background_tasks)
        finally:
            await self.shutdown()


def build_app_runtime(
    config: Config,
    workspace: Path | None = None,
    *,
    features: RuntimeFeatures = SERVICE_RUNTIME_FEATURES,
) -> AppRuntime:
    return AppRuntime(
        config,
        workspace or resolve_default_workspace(),
        features=features,
    )
