"""Compose explicit SDK service fakes for service plugin setup."""

from pathlib import Path
from shiori_sdk.core.services import (
    BACKGROUND_RESULTS,
    EXTERNAL_TURNS,
    HTTP,
    KV,
    LIGHT_MODEL,
    LIGHT_PROVIDER,
    MODELS,
    PROCESSES,
    PROCESS_RESOURCES,
    RESOURCES,
    ROLES,
    RPC,
    RUNTIME,
    SESSION_STORE,
    TOOLS,
    TOOL_TURN,
)
from shiori_sdk.models import ChatProvider
from .extensions import FakeExtensionContext
from .memory_context import FakeRpc
from .processes import FakeProcesses, current_tool_turn
from .roles import FakeRoles
from .tools import FakeTools
from .storage import FakeKV
from .resources import FakeResources
from .sessions import FakeSessions
from .external_turns import FakeExternalTurns
from .background_results import FakeBackgroundResults
from .process_resources import FakeProcessResources
from .http import FakeHttp
from .runtime import FakeRuntimeLifecycle
from .models import FakeChatProvider, FakeModels


class FakeServiceContext(FakeExtensionContext):
    """No real transport, process, role store, session store or runtime is created."""

    def __init__(
        self,
        plugin_id: str,
        workspace: Path,
        *,
        config: dict[str, object] | None = None,
        package_dir: Path | None = None,
        inject: tuple[str, ...] = (),
    ):
        """``package_dir`` declares inject from that package's manifest."""
        super().__init__(
            plugin_id,
            workspace=workspace,
            config=config,
            package_dir=package_dir,
            inject=inject,
        )
        self.fake_roles = FakeRoles(workspace)
        self.fake_models = FakeModels()
        self.fake_sessions = FakeSessions()
        self.fake_external_turns = FakeExternalTurns()
        self.fake_background_results = FakeBackgroundResults()
        self.fake_process_resources = FakeProcessResources()
        self.fake_tools = FakeTools()
        self.fake_kv = FakeKV()
        self.fake_rpc = FakeRpc()
        self.fake_http = FakeHttp()
        self.fake_resources = FakeResources(workspace)
        self.fake_processes = FakeProcesses()
        self.fake_runtime = FakeRuntimeLifecycle()
        self.effect("process_resources", self.fake_process_resources.close)
        self.fake_light_provider: ChatProvider = FakeChatProvider()
        self.serve(ROLES, self.fake_roles)
        self.serve(MODELS, self.fake_models)
        self.serve(SESSION_STORE, self.fake_sessions)
        self.serve(EXTERNAL_TURNS, self.fake_external_turns)
        self.serve(BACKGROUND_RESULTS, self.fake_background_results)
        self.serve(PROCESS_RESOURCES, self.fake_process_resources)
        self.serve(TOOLS, self.fake_tools)
        self.serve(KV, self.fake_kv)
        self.serve(RPC, self.fake_rpc)
        self.serve(HTTP, self.fake_http)
        self.serve(RESOURCES, self.fake_resources)
        self.serve(PROCESSES, self.fake_processes)
        self.serve(RUNTIME, self.fake_runtime)
        self.serve(TOOL_TURN, current_tool_turn)
        self.serve(LIGHT_PROVIDER, self.fake_light_provider)
        self.serve(LIGHT_MODEL, "fake-light-model")

    async def aclose(self) -> None:
        """Dispose plugin resources then clear the fixture's scoped registrations."""
        try:
            await super().aclose()
        finally:
            self.fake_tools.tools.clear()
            self.fake_rpc.handlers.clear()
            self.fake_rpc.concurrency.clear()
            self.fake_rpc.admission_exempt.clear()
