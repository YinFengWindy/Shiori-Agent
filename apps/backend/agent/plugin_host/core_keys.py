"""Transitional core keys the host assembly layer reads v2 capabilities from (#901).

Core modules provide these keys to the kernel before any plugin starts, so the
assembly layer builds each plugin's v2 context without importing them. A
capability scoped to one plugin comes from a ``PluginCapabilityBinder`` whose
``for_plugin`` returns the existing v2 view for that plugin's binding. The
``host.`` prefix keeps these names apart from the public core keys plugins
will inject by manifest name in P4 (``shiori_sdk.core``).
"""

from __future__ import annotations

from collections.abc import Callable, Iterable
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol

from shiori_sdk.diagnostics import Diagnostics
from shiori_sdk.kernel import Key, Scope
from shiori_sdk.runtime import HostServiceUnavailable

from agent.plugin_host.call_gate import PluginCallGate
from agent.plugin_host.capabilities import PluginContributions


@dataclass(frozen=True)
class PluginBinding:
    """One plugin activation as seen by the binders that scope capabilities to it.

    ``scope`` releases what the capability registered when the plugin stops,
    ``contributions`` collects the objects the host aggregates across plugins,
    and ``calls`` admits or refuses calls into the plugin. ``namespace`` is the
    kernel generation's import namespace. ``plugin_roots`` labels the directory
    of every plugin this generation discovered, for traceback attribution.
    """

    plugin_id: str
    namespace: str
    scope: Scope
    contributions: PluginContributions
    calls: PluginCallGate
    plugin_roots: tuple[tuple[str, Path], ...]


class PluginCapabilityBinder[T](Protocol):
    """A core service that hands each plugin its own v2 capability view."""

    def for_plugin(self, binding: PluginBinding) -> T:
        """The capability object for the plugin ``binding`` describes."""
        ...


class CoreProvide(Protocol):
    """What a core module is given to publish its services: ``Kernel.provide``."""

    def __call__[T](self, key: Key[T], impl: T) -> None: ...


CoreModule = Callable[[CoreProvide], None]
"""Provides one core module's keys; raising aborts startup (§8.5)."""

HOST_DIAGNOSTICS: Key[PluginCapabilityBinder[Diagnostics]] = Key("host.diagnostics")
"""The ``diagnostics`` capability, built over ``CRASH_REPORTING``."""

HOST_CONFIG_REFERENCES: Key[Callable[[str], str]] = Key("host.config_references")
"""Expands ``${NAME}`` references in plugin-stored values (``config``)."""

# capability -> the core keys backing it. A plugin that declares the capability
# while a key is not provided fails before setup, like a missing host service.
CAPABILITY_CORE_KEYS: dict[str, tuple[Key[Any], ...]] = {
    "config": (HOST_CONFIG_REFERENCES,),
    "diagnostics": (HOST_DIAGNOSTICS,),
}


def require_core_keys(
    plugin_id: str,
    capabilities: Iterable[str],
    provided: Callable[[Key[Any]], object],
) -> None:
    """Fails before setup when a declared capability's core key has no provider.

    ``provided`` looks a key up in the kernel (``Kernel.get``).
    """
    for capability in capabilities:
        missing = [
            key.name
            for key in CAPABILITY_CORE_KEYS.get(capability, ())
            if provided(key) is None
        ]
        if missing:
            raise HostServiceUnavailable.for_capability(plugin_id, capability, missing)
