"""Independent setup doubles for tool, command and observation plugins."""

import asyncio
from collections.abc import Coroutine
from pathlib import Path
from shiori_sdk.sessions import SessionUndo
from shiori_sdk.memory.engine import MemoryEngine
from shiori_sdk.extensions import Dependencies
from shiori_sdk.runtime import HostServiceUnavailable
from .context import FakePluginContext
from .hooks import FakeToolHooks
from .diagnostics import FakeDiagnostics
from .memory import FakeMemoryStorage


class FakeConfig:
    """Resolved values owned by one test."""

    def __init__(self, values: dict[str, object] | None = None):
        self.values = values or {}
        self.references: dict[str, str] = {}

    def as_dict(self) -> dict[str, object]:
        """Return an isolated snapshot for plugin validation."""
        return dict(self.values)

    def resolve_reference(self, value: str) -> str:
        """Return a test-provided runtime resolution, keeping unknown references unchanged."""
        return self.references.get(value, value)


class FakeBotCommands:
    """Record command-menu registration."""

    def __init__(self):
        self.commands: list[tuple[str, str]] = []

    def add(self, command: str, description: str) -> None:
        """Record one contribution."""
        self.commands.append((command, description))


class FakeDependencies:
    """Mutable current exports, resolved again at every lookup."""

    def __init__(self, exports: dict[str, object] | None = None):
        self.exports = exports if exports is not None else {}

    def require(self, plugin_id: str) -> object:
        """Resolve an explicitly provided required export."""
        return self.exports[plugin_id]

    def get_optional(self, plugin_id: str) -> object | None:
        """Read current availability without caching an earlier provider."""
        return self.exports.get(plugin_id)


class FakeBackground:
    """Run real asyncio tasks while delegating lifetime to a fake context."""

    def __init__(self, context: FakePluginContext):
        self.context = context

    def spawn[T](
        self, coro: Coroutine[object, object, T], *, name: str
    ) -> asyncio.Task[T]:
        """Start one task and register reverse-order cancellation."""
        task = asyncio.create_task(coro, name=f"plugin:{self.context.plugin_id}:{name}")

        async def cancel() -> None:
            if task.done():
                return
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass

        self.context.effect(f"background:{name}", cancel)
        return task

    def spawn_runtime[T](
        self, coro: Coroutine[object, object, T], *, name: str
    ) -> asyncio.Task[T]:
        """Exercise real scheduling without a host generation lease."""
        return self.spawn(coro, name=name)


class FakeExtensionContext(FakePluginContext):
    """Inject only SDK fakes; no host install, config, database or session services.

    ``workspace`` and ``session_manager`` left as ``None`` model a host that lacks
    the service: reading them raises ``HostServiceUnavailable`` like the host does.
    ``memory_engine`` stays optional because the host has none when memory is off.
    """

    def __init__(
        self,
        plugin_id: str,
        *,
        workspace: Path | None = None,
        config: dict[str, object] | None = None,
        dependencies: Dependencies | None = None,
        session_manager: SessionUndo | None = None,
        memory_engine: MemoryEngine | None = None,
    ):
        super().__init__(plugin_id)
        self._workspace = workspace
        self.config = FakeConfig(config)
        self.tool_hooks = FakeToolHooks()
        self.bot_commands = FakeBotCommands()
        self.dependencies = dependencies or FakeDependencies()
        self._session_manager = session_manager
        self.memory_engine = memory_engine
        self.background = FakeBackground(self)
        self.diagnostics = FakeDiagnostics()
        self.storage = FakeMemoryStorage()

    @property
    def workspace(self) -> Path:
        """Returns the supplied workspace, failing like a host that has none."""
        if self._workspace is None:
            raise HostServiceUnavailable(
                f"插件 {self.plugin_id} 声明了 capability 'workspace'，"
                "但宿主未提供服务 workspace"
            )
        return self._workspace

    @property
    def session_manager(self) -> SessionUndo:
        """Returns the supplied session undo service, failing like a host without one."""
        if self._session_manager is None:
            raise HostServiceUnavailable(
                f"插件 {self.plugin_id} 声明了 capability 'session_manager'，"
                "但宿主未提供服务 session_manager"
            )
        return self._session_manager

    async def aclose(self) -> None:
        """Remove subscriptions and reverse cleanups, then clear contributions."""
        try:
            await super().aclose()
        finally:
            self.tool_hooks.handlers.clear()
            self.bot_commands.commands.clear()
