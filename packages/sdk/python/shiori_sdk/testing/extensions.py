"""Independent setup doubles for tool, command and observation plugins."""

import asyncio
from collections.abc import Coroutine
from pathlib import Path
from shiori_sdk.extensions import Dependencies
from shiori_sdk.kernel import Kernel
from shiori_sdk.runtime import HostServiceUnavailable
from .context import FakePluginContext
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

    ``workspace`` left as ``None`` models a host that lacks the service:
    reading it raises ``HostServiceUnavailable`` like the host does.
    ``kernel``, ``inject``, ``optional_inject`` and ``package_dir`` are those
    of ``FakePluginContext``: provide a ``CommandRegistry`` as ``COMMANDS`` on
    ``kernel`` for a command plugin, a ``FakeSessions`` as ``SESSIONS`` when
    the command rolls a turn back, and ``MEMORY_ENGINE`` when the test has one.
    """

    def __init__(
        self,
        plugin_id: str,
        *,
        workspace: Path | None = None,
        config: dict[str, object] | None = None,
        dependencies: Dependencies | None = None,
        kernel: Kernel | None = None,
        inject: tuple[str, ...] = (),
        optional_inject: tuple[str, ...] = (),
        package_dir: Path | None = None,
    ):
        super().__init__(
            plugin_id,
            kernel=kernel,
            inject=inject,
            optional_inject=optional_inject,
            package_dir=package_dir,
        )
        self._workspace = workspace
        self.config = FakeConfig(config)
        self.dependencies = dependencies or FakeDependencies()
        self.background = FakeBackground(self)
        self.storage = FakeMemoryStorage()

    @property
    def workspace(self) -> Path:
        """Returns the supplied workspace, failing like a host that has none."""
        if self._workspace is None:
            raise HostServiceUnavailable.for_capability(
                self.plugin_id, "workspace", ("workspace",)
            )
        return self._workspace
