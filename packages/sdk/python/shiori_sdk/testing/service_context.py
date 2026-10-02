"""One explicit SDK setup fixture for role, generation and native plugins."""

from collections.abc import Awaitable, Callable
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Literal
from shiori_sdk.models import ModelSnapshot, ChatProvider
from shiori_sdk.roles import RoleView
from shiori_sdk.plugin_services import ServicePluginContext
from .extensions import FakeExtensionContext
from .memory_context import FakeRpc
from .processes import FakeProcesses, current_tool_turn
from .roles import FakeRoles
from .services import FakeTools, FakeKV, FakeResources, FakeSessions, FakeHttp


class FakeModels:
    """Select explicitly seeded snapshots and record the requested role/purpose."""

    def __init__(self):
        self.snapshots: dict[tuple[str, str], ModelSnapshot] = {}
        self.activations: list[tuple[str, str]] = []

    @asynccontextmanager
    async def activate(self, role_id: str, purpose: Literal["chat", "vision"]):
        """Hold a test-supplied snapshot over an awaited operation."""
        self.activations.append((role_id, purpose))
        yield self.snapshots[role_id, purpose]


class FakeRuntimeLifecycle:
    """Record drain requests without constructing a host generation."""

    def __init__(self):
        self.was_active = False
        self.drainers: list[Callable[[], Awaitable[None]]] = []

    def on_drain(self, callback: Callable[[], Awaitable[None]]) -> None:
        """Retain a drainer for an explicit test transition."""
        self.drainers.append(callback)


class FakeSceneObservations:
    """Retain observation predicates as fixture-visible contributions."""

    def __init__(self):
        self.predicates: list[Callable[[RoleView], bool]] = []

    def request(self, predicate: Callable[[RoleView], bool]) -> None:
        """Record demand without starting a scene observer."""
        self.predicates.append(predicate)


class FakeServiceContext(FakeExtensionContext):
    """No real transport, process, role store, session store or runtime is created."""

    def __init__(
        self,
        plugin_id: str,
        workspace: Path,
        *,
        config: dict[str, object] | None = None,
    ):
        super().__init__(plugin_id, workspace=workspace, config=config)
        self.roles = FakeRoles(workspace)
        self.models = FakeModels()
        self.sessions = FakeSessions()
        self.tools = FakeTools()
        self.kv = FakeKV()
        self.rpc = FakeRpc()
        self.http = FakeHttp()
        self.resources = FakeResources(workspace)
        self.processes = FakeProcesses()
        self.tool_turn = current_tool_turn
        self.runtime = FakeRuntimeLifecycle()
        self.scene_observations = FakeSceneObservations()
        self.light_provider: ChatProvider | None = None
        self.light_model = ""

    def as_capability(self) -> ServicePluginContext:
        """Check that fake and actual host implement the same setup surface."""
        return self

    async def aclose(self) -> None:
        """Dispose plugin resources then clear the fixture's scoped registrations."""
        try:
            await super().aclose()
        finally:
            self.tools.tools.clear()
            self.rpc.handlers.clear()
            self.scene_observations.predicates.clear()
