"""Compose explicit SDK capability fixtures for service plugin setup."""

from pathlib import Path
from shiori_sdk.models import ChatProvider
from shiori_sdk.plugin_services import ServicePluginContext
from .extensions import FakeExtensionContext
from .memory_context import FakeRpc
from .processes import FakeProcesses, current_tool_turn
from .roles import FakeRoles
from .tools import FakeTools
from .storage import FakeKV
from .resources import FakeResources
from .sessions import FakeSessions
from .external_turns import FakeExternalTurns
from .http import FakeHttp
from .runtime import FakeRuntimeLifecycle
from .scene_observations import FakeSceneObservations
from .models import FakeChatProvider, FakeModels


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
        self.external_turns = FakeExternalTurns()
        self.tools = FakeTools()
        self.kv = FakeKV()
        self.rpc = FakeRpc()
        self.http = FakeHttp()
        self.resources = FakeResources(workspace)
        self.processes = FakeProcesses()
        self.tool_turn = current_tool_turn
        self.runtime = FakeRuntimeLifecycle()
        self.scene_observations = FakeSceneObservations()
        self.light_provider: ChatProvider = FakeChatProvider()
        self.light_model = "fake-light-model"

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
            self.rpc.concurrency.clear()
            self.rpc.admission_exempt.clear()
            self.scene_observations.predicates.clear()
