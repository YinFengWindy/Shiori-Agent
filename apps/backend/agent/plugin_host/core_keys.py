"""Transitional core keys the host assembly layer reads v2 capabilities from (#901).

Core modules provide these keys to the kernel before any plugin starts, so the
assembly layer builds each plugin's v2 context without importing them. The
``host.`` prefix keeps these names apart from the public core keys plugins
will inject by manifest name in P4 (``shiori_sdk.core``).

Wiring one capability to a core module takes three edits: its key here, its
row in ``CORE_CAPABILITIES`` and the provide call in ``bootstrap.plugin_core``;
the v2 context property then reads it through ``_core_capability``. A
capability whose contributions the host aggregates is a
``PluginContributionService`` over ``capabilities.ContributionsByPlugin``.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass
from typing import Any, Protocol

from shiori_sdk.accounts.capability import AccountsCapability
from shiori_sdk.channels import Channel
from shiori_sdk.channels.avatars import AvatarsCapability
from shiori_sdk.channels.context import ChannelsCapability
from shiori_sdk.diagnostics import Diagnostics
from shiori_sdk.processes import ToolTurn
from shiori_sdk.tool_hooks import ToolHooksCapability
from shiori_sdk.tools import ToolsCapability
from shiori_sdk.kernel import Key, Scope
from shiori_sdk.runtime import HostServiceUnavailable

from agent.plugin_host.call_gate import PluginCallGate
from agent.plugin_host.capabilities import PluginContributions
from agent.plugin_host.manifest import PluginManifest


@dataclass(frozen=True)
class PluginBinding:
    """One plugin activation, for the binders that scope a capability to it.

    ``scope`` releases what the capability registered when the plugin stops,
    ``contributions`` collects the objects the host aggregates across plugins,
    and ``calls`` admits or refuses calls into the plugin. ``namespace`` is the
    kernel generation's import namespace; ``manifest`` is the plugin's parsed
    manifest, for the static declarations a capability checks against.
    """

    plugin_id: str
    namespace: str
    manifest: PluginManifest
    scope: Scope
    contributions: PluginContributions
    calls: PluginCallGate


class PluginCapabilityBinder[T](Protocol):
    """A core service that hands each plugin its own v2 capability view."""

    def for_plugin(self, binding: PluginBinding) -> T:
        """The capability object for the plugin ``binding`` describes."""
        ...


class ActiveContributions[T](Protocol):
    """Objects plugins contributed, read back for the active plugins only."""

    def active(self, plugin_ids: Iterable[str]) -> Sequence[T]:
        """The contributions of ``plugin_ids`` (kernel order), in that order."""
        ...


class PluginContributionService[C, T](
    PluginCapabilityBinder[C], ActiveContributions[T], Protocol
):
    """A per-plugin capability ``C`` whose contributions ``T`` the host aggregates.

    Each plugin adds through its own ``for_plugin`` view; consumers read the
    active plugins' contributions with ``active``.
    ``capabilities.ContributionsByPlugin`` is the shared storage behind it.
    """


class CoreProvide(Protocol):
    """What a core module is given to publish its services: ``Kernel.provide``."""

    def __call__[T](self, key: Key[T], impl: T) -> None: ...


CoreModule = Callable[[CoreProvide], None]
"""Provides one core module's keys; raising aborts startup (§8.5)."""

HOST_DIAGNOSTICS: Key[Diagnostics] = Key("host.diagnostics")
"""The ``diagnostics`` capability, built over ``CRASH_REPORTING``."""

HOST_TOOLS: Key[PluginCapabilityBinder[ToolsCapability]] = Key("host.tools")
"""The ``tools`` capability over the host ``ToolRegistry`` (``agent.tools``)."""


# The hook type (``agent.tool_hooks.ToolHook``) is a host module this layer may
# not import, so the key leaves it open; ``PluginToolHooks`` types it exactly.
HOST_TOOL_HOOKS: Key[PluginContributionService[ToolHooksCapability, Any]] = Key(
    "host.tool_hooks"
)
"""The ``tool_hooks`` capability (``agent.tool_hooks``)."""

HOST_TOOL_TURN: Key[Callable[[], ToolTurn]] = Key("host.tool_turn")
"""The ``tool_turn`` capability: the tool turn running in the current task."""

HOST_CHANNELS: Key[PluginContributionService[ChannelsCapability, Channel]] = Key(
    "host.channels"
)
"""The ``channels`` capability: transports plugins contribute (``core.channels``)."""


class GenerationAccounts(PluginCapabilityBinder[AccountsCapability], Protocol):
    """The ``host.accounts`` service: one kernel generation's account index.

    Plugins register into the generation's own index; ``publish`` makes it the
    one routing, sending and the UI see, and ``drop`` discards it once the
    generation is retired or abandoned.
    """

    def publish(self) -> None:
        """Makes this generation's account reports authoritative."""
        ...

    def drop(self) -> None:
        """Discards this generation's account index."""
        ...


HOST_ACCOUNTS: Key[GenerationAccounts] = Key("host.accounts")
"""The ``accounts`` capability over the ``AccountRegistry`` (``core.accounts``)."""

HOST_AVATARS: Key[PluginCapabilityBinder[AvatarsCapability]] = Key("host.avatars")
"""The ``avatars`` capability over the shared avatar cache (``core.channels``)."""

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
    "tools": CoreCapability(HOST_TOOLS, per_plugin=True),
    "tool_hooks": CoreCapability(HOST_TOOL_HOOKS, per_plugin=True),
    "tool_turn": CoreCapability(HOST_TOOL_TURN),
    "channels": CoreCapability(HOST_CHANNELS, per_plugin=True),
    "accounts": CoreCapability(HOST_ACCOUNTS, per_plugin=True),
    "avatars": CoreCapability(HOST_AVATARS, per_plugin=True),
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
