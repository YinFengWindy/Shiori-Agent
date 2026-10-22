"""Transitional core keys the host assembly layer reads v2 capabilities from (#901).

Core modules provide these keys to the kernel before any plugin starts, so the
assembly layer builds each plugin's v2 context without importing them. The
``host.`` prefix keeps these names apart from the public core keys plugins
will inject by manifest name in P4 (``shiori_sdk.core``).

Wiring one capability to a core module takes three edits: its key here, its
row in ``CORE_CAPABILITIES`` and the provide call in ``bootstrap.plugin_core``.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass
from typing import Any, Protocol

from shiori_sdk.diagnostics import Diagnostics
from shiori_sdk.kernel import Key, Scope
from shiori_sdk.runtime import HostServiceUnavailable

from agent.plugin_host.call_gate import PluginCallGate
from agent.plugin_host.capabilities import PluginContributions


@dataclass(frozen=True)
class PluginBinding:
    """One plugin activation, for the binders that scope a capability to it.

    ``scope`` releases what the capability registered when the plugin stops,
    ``contributions`` collects the objects the host aggregates across plugins,
    and ``calls`` admits or refuses calls into the plugin. ``namespace`` is the
    kernel generation's import namespace.
    """

    plugin_id: str
    namespace: str
    scope: Scope
    contributions: PluginContributions
    calls: PluginCallGate


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

HOST_DIAGNOSTICS: Key[Diagnostics] = Key("host.diagnostics")
"""The ``diagnostics`` capability, built over ``CRASH_REPORTING``."""

HOST_CONFIG_REFERENCES: Key[Callable[[str], str]] = Key("host.config_references")
"""Expands ``${NAME}`` references for ``config.resolve_reference``.

Not a capability row: the assembly layer itself needs it for every plugin's
``config``, so each generation requires it when it is constructed.
"""


@dataclass(frozen=True)
class CoreCapability:
    """Where a v2 capability comes from: the core key that provides it.

    ``per_plugin`` marks a key whose provider is a ``PluginCapabilityBinder``;
    the plugin then gets ``for_plugin(binding)``. Otherwise the provided
    instance itself is the capability, shared by every plugin.
    """

    key: Key[Any]
    per_plugin: bool = False


# v2 capability name (which is also the plugin context argument it fills) ->
# the core key behind it. Rows move here from ``CAPABILITY_HOST_SERVICES``
# (``host_service_requirements.py``) as 2b–2f give each capability a core
# provider; 2g deletes that table together with ``HostServices``. They cannot
# merge earlier: the other table names ``HostServices`` attributes, which only
# exist until then.
CORE_CAPABILITIES: Mapping[str, CoreCapability] = {
    "diagnostics": CoreCapability(HOST_DIAGNOSTICS),
}


def bind_core_capabilities(
    capabilities: Iterable[str],
    provided: Callable[[Key[Any]], object],
    binding: PluginBinding,
) -> dict[str, Any]:
    """Plugin context arguments for the declared capabilities the core provides.

    ``provided`` looks a key up in the kernel (``Kernel.get``). A declared
    capability whose key nobody provides fails before setup, like a missing
    host service.
    """
    arguments: dict[str, Any] = {}
    for capability in capabilities:
        if (row := CORE_CAPABILITIES.get(capability)) is None:
            continue
        value: Any = provided(row.key)
        if value is None:
            raise HostServiceUnavailable.for_capability(
                binding.plugin_id, capability, [row.key.name]
            )
        arguments[capability] = value.for_plugin(binding) if row.per_plugin else value
    return arguments


def required_core_key[T](provided: Callable[[Key[T]], T | None], key: Key[T]) -> T:
    """The provider of a key the assembly layer cannot run without."""
    if (value := provided(key)) is None:
        raise HostServiceUnavailable(f"宿主未提供核心服务 {key.name}")
    return value
