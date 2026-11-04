"""Explicit plugin dependencies and generation-scoped exported APIs."""

from collections.abc import Callable
from typing import Any


class PluginDependencyError(RuntimeError):
    """A declared dependency is unavailable or forms a dependency cycle."""


class PluginDependencies:
    """Allows a plugin to read only the APIs of its declared dependencies."""

    def __init__(
        self,
        declared: tuple[str, ...],
        resolve: Callable[[str, bool], Any],
        *,
        optional_declared: tuple[str, ...] = (),
    ):
        self._declared = declared
        self._optional_declared = optional_declared
        self._resolve = resolve

    def require(self, plugin_id: str) -> Any:
        """Returns the active dependency's public API within the same generation."""
        if plugin_id not in self._declared:
            raise PluginDependencyError(f"未声明插件依赖: {plugin_id}")
        return self._resolve(plugin_id, False)

    def get_optional(self, plugin_id: str) -> Any | None:
        """Read an optional API now; unavailable or unexported providers yield None.

        Look up again for each operation so a provider unload/reload cannot leave
        the consumer using an old export. This does not activate the provider.
        """
        if plugin_id not in self._optional_declared:
            raise PluginDependencyError(f"未声明可选插件依赖: {plugin_id}")
        return self._resolve(plugin_id, True)
