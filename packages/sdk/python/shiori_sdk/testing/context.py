"""A pure contract setup context with explicitly granted fake capabilities."""

import inspect
from pathlib import Path

from shiori_sdk.kernel import Context, Kernel, Key, PluginSpec, Scope, Veto
from shiori_sdk.kernel.events import OnHandler, WatchHandler
from shiori_sdk.runtime import (
    CapabilityNotGranted,
    Dispose,
    require_known_capabilities,
)
from .events import FakeEvents
from .lifecycle import FakeLifecycle


class FakePluginContext:
    """Records setup effects and exports without instantiating any host services.

    ``capabilities`` are the grants, normally a manifest's declaration (see the
    ``sdk_context`` fixture); names unknown to the host are rejected like the host
    does. Only ``lifecycle`` and ``events`` have fakes here; other declared names
    are recorded in ``granted`` for specialized fakes.

    The kernel members (``provide`` / ``require`` / ``get``, ``on`` / ``watch``
    / ``emit``) run on a real ``Kernel``: ``kernel`` (a fresh one by default)
    with ``inject`` / ``optional_inject`` / ``provides`` as the manifest
    declares them. Provide core stubs on ``kernel`` before calling setup.
    """

    def __init__(
        self,
        plugin_id: str = "test_plugin",
        plugin_dir: Path = Path("."),
        *,
        capabilities: tuple[str, ...] = ("lifecycle", "events"),
        kernel: Kernel | None = None,
        inject: tuple[str, ...] = (),
        optional_inject: tuple[str, ...] = (),
        provides: tuple[str, ...] = (),
    ) -> None:
        require_known_capabilities(capabilities, f"FakePluginContext({plugin_id})")
        self.plugin_id = plugin_id
        self.plugin_dir = plugin_dir
        self.granted = tuple(sorted(set(capabilities)))
        self.exported: object | None = None
        self._lifecycle = FakeLifecycle()
        self._events = FakeEvents()
        self._effects: list[tuple[str, Dispose]] = []
        self._closed = False
        self.kernel = kernel if kernel is not None else Kernel()
        self._scope = Scope(plugin_id)
        spec = PluginSpec(
            plugin_id,
            _no_setup,
            requires=inject,
            optional=optional_inject,
            provides=provides,
        )
        self._kernel_context = Context(self.kernel, spec, self._scope)

    def _check(self, name: str) -> None:
        if self._closed:
            raise RuntimeError("Plugin scope is closed")
        if name not in self.granted:
            raise CapabilityNotGranted(
                f"插件 {self.plugin_id} 未声明 capability '{name}'"
            )

    @property
    def lifecycle(self) -> FakeLifecycle:
        """Returns the granted lifecycle fake."""
        self._check("lifecycle")
        return self._lifecycle

    @property
    def events(self) -> FakeEvents:
        """Returns the granted event fake."""
        self._check("events")
        return self._events

    def expose(self, api: object) -> None:
        """Records a plugin's public export."""
        if self._closed:
            raise RuntimeError("Plugin scope is closed")
        self.exported = api

    def provide[T](self, key: Key[T], impl: T) -> None:
        """Publishes ``impl`` on ``kernel`` under a declared ``provides`` key."""
        self._kernel_context.provide(key, impl)

    def require[T](self, key: Key[T]) -> T:
        """The provider of a declared ``inject`` key on ``kernel``."""
        return self._kernel_context.require(key)

    def get[T](self, key: Key[T]) -> T | None:
        """The provider of a declared ``optional_inject`` key on ``kernel``, or None."""
        return self._kernel_context.get(key)

    def on[E](self, event_type: type[E], handler: OnHandler[E]) -> None:
        """Joins ``kernel``'s ordered chain of ``event_type``."""
        self._kernel_context.on(event_type, handler)

    def watch[E](self, event_type: type[E], handler: WatchHandler[E]) -> None:
        """Listens read-only to ``event_type`` on ``kernel``."""
        self._kernel_context.watch(event_type, handler)

    async def emit[E](self, event: E) -> E | Veto:
        """Emits through ``kernel``."""
        return await self._kernel_context.emit(event)

    def effect(self, label: str, dispose: Dispose) -> None:
        """Records custom cleanup in registration order."""
        if self._closed:
            raise RuntimeError("Plugin scope is closed")
        self._effects.append((label, dispose))

    async def aclose(self) -> None:
        """Stops subscriptions, then runs all cleanup in reverse registration order."""
        self._closed = True
        self._events.close()
        self._lifecycle.close()
        errors: list[Exception] = await self._scope.close()
        while self._effects:
            _, dispose = self._effects.pop()
            try:
                result = dispose()
                if inspect.isawaitable(result):
                    await result
            except Exception as error:
                errors.append(error)
        if errors:
            raise ExceptionGroup("Plugin cleanup failed", errors)


async def _no_setup(context: Context) -> None:
    """The fake's spec is never set up by the kernel; setup runs in the test."""
