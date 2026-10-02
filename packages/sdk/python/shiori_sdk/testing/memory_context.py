"""Independent setup doubles for memory plugin RPC and document contracts."""

from pathlib import Path

from shiori_sdk.memory.engine import MemoryEngine
from shiori_sdk.rpc import Concurrency, RpcHandler

from .context import FakePluginContext
from .memory import FakeMemoryRoles, FakeMemoryStorage


class FakeRpc:
    """Records registrations and their declared concurrency policy."""

    def __init__(self):
        self.handlers: dict[str, RpcHandler] = {}
        self.concurrency: dict[str, Concurrency] = {}
        self.events: list[tuple[str, dict[str, object]]] = []

    def register(
        self,
        name: str,
        handler: RpcHandler,
        *,
        concurrency: Concurrency = Concurrency.MUTATION,
    ) -> None:
        self.handlers[name] = handler
        self.concurrency[name] = concurrency

    async def emit(self, name: str, payload: dict[str, object]) -> bool:
        """Record one plugin event for assertion."""
        self.events.append((name, payload))
        return True


class FakeMemoryCapability:
    """Stores setup inputs without opening role or host databases."""

    def __init__(
        self,
        workspace: Path,
        *,
        engine: MemoryEngine | None = None,
        roles: FakeMemoryRoles | None = None,
    ):
        self.workspace = workspace
        self.engine = engine
        self.roles = roles or FakeMemoryRoles()
        self.storage = FakeMemoryStorage()
        self.documents: dict[str, list[dict[str, object]]] = {}

    async def read_documents(self, payload: dict[str, object]) -> dict[str, object]:
        role_id = str(payload.get("role_id") or "")
        if not self.roles.exists(role_id):
            raise ValueError(f"role not found: {role_id}")
        return {"role_id": role_id, "documents": self.documents.get(role_id, [])}


class FakeMemoryPluginContext(FakePluginContext):
    """Setup context with fake memory and RPC capabilities."""

    def __init__(
        self,
        workspace: Path,
        *,
        engine: MemoryEngine | None = None,
        roles: FakeMemoryRoles | None = None,
        plugin_dir: Path = Path("."),
    ):
        super().__init__("default_memory", plugin_dir)
        self.memory = FakeMemoryCapability(workspace, engine=engine, roles=roles)
        self.rpc = FakeRpc()

    async def aclose(self):
        await super().aclose()
        self.rpc.handlers.clear()
        self.rpc.concurrency.clear()
