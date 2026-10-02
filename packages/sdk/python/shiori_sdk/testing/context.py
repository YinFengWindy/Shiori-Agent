"""A pure contract setup context with explicitly granted fake capabilities."""

import inspect
from pathlib import Path

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
    """

    def __init__(
        self,
        plugin_id: str = "test_plugin",
        plugin_dir: Path = Path("."),
        *,
        capabilities: tuple[str, ...] = ("lifecycle", "events"),
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
        errors: list[Exception] = []
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
