"""Independent setup doubles for memory plugin RPC and document contracts."""

from pathlib import Path

from shiori_sdk.kernel import Kernel
from shiori_sdk.rpc import Concurrency, RpcHandler

from .context import FakePluginContext
from .memory import FakeMemoryRoles, FakeMemoryStorage


class FakeRpc:
    """Records registrations and their declared concurrency policy."""

    def __init__(self):
        self.handlers: dict[str, RpcHandler] = {}
        self.concurrency: dict[str, Concurrency] = {}
        self.admission_exempt: dict[str, bool] = {}
        self.events: list[tuple[str, dict[str, object]]] = []

    def register(
        self,
        name: str,
        handler: RpcHandler,
        *,
        concurrency: Concurrency = Concurrency.MUTATION,
        admission_exempt: bool = False,
    ) -> None:
        self.handlers[name] = handler
        self.concurrency[name] = concurrency
        self.admission_exempt[name] = admission_exempt

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
        roles: FakeMemoryRoles | None = None,
        skills: tuple[str, ...] = (),
    ):
        self.workspace = workspace
        self.roles = roles or FakeMemoryRoles()
        self.storage = FakeMemoryStorage()
        self.documents: dict[str, list[dict[str, object]]] = {}
        self._skills = list(skills)

    def skill_names(self) -> list[str]:
        """Names the test listed; the host implementation reads the skill dirs."""
        return list(self._skills)

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
        roles: FakeMemoryRoles | None = None,
        skills: tuple[str, ...] = (),
        plugin_dir: Path = Path("."),
        kernel: Kernel | None = None,
        inject: tuple[str, ...] = (),
        optional_inject: tuple[str, ...] = (),
        provides: tuple[str, ...] = (),
        package_dir: Path | None = None,
    ):
        super().__init__(
            "default_memory",
            plugin_dir,
            kernel=kernel,
            inject=inject,
            optional_inject=optional_inject,
            provides=provides,
            package_dir=package_dir,
        )
        self.memory = FakeMemoryCapability(workspace, roles=roles, skills=skills)
        self.rpc = FakeRpc()

    async def aclose(self):
        await super().aclose()
        self.rpc.handlers.clear()
        self.rpc.concurrency.clear()
        self.rpc.admission_exempt.clear()
