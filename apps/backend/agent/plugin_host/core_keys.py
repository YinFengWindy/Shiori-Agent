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

Core service classes are named by what the key holds. ``Plugin*`` (such as
``PluginTools`` or ``PluginChannels``) is a binder with ``for_plugin``, or an
aggregating service over ``ContributionsByPlugin``: each plugin gets its own
view. ``Host*`` (such as ``HostRoles`` or ``HostSessions``) is itself the
capability, one instance per generation shared by every plugin.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol

from shiori_sdk.accounts.capability import AccountsCapability
from shiori_sdk.background_results import BackgroundResults
from shiori_sdk.channels import Channel
from shiori_sdk.channels.avatars import AvatarsCapability
from shiori_sdk.channels.context import ChannelsCapability
from shiori_sdk.diagnostics import Diagnostics
from shiori_sdk.extensions import BackgroundTasks
from shiori_sdk.external_turns import ExternalTurns
from shiori_sdk.http import HttpClient
from shiori_sdk.memory.context import MemoryCapability
from shiori_sdk.memory.engine import MemoryEngine
from shiori_sdk.models import ChatProvider, RoleModels
from shiori_sdk.process_resources import PluginProcessResources
from shiori_sdk.processes import Processes, Resources, ToolTurn
from shiori_sdk.roles import Roles, SceneObservations
from shiori_sdk.rpc import RpcCapability
from shiori_sdk.sessions import PluginSessions, SessionUndo
from shiori_sdk.tools import ToolsCapability
from shiori_sdk.kernel import Key, Scope
from shiori_sdk.runtime import EventsCapability, HostServiceUnavailable

from agent.plugin_host.call_gate import PluginCallGate
from agent.plugin_host.manifest import PluginManifest
from agent.plugin_host.rpc import PluginRpcRegistry


@dataclass(frozen=True)
class PluginBinding:
    """One plugin activation, for the binders that scope a capability to it.

    ``scope`` releases what the capability registered when the plugin stops,
    and ``calls`` admits or refuses calls into the plugin. ``namespace`` is the
    kernel generation's import namespace; ``manifest`` is the plugin's parsed
    manifest, for the static declarations a capability checks against.

    Only the plugin's identity and static declarations (manifest), its scope
    and its call gate belong here. Data one capability alone needs stays with
    that capability's core service, never in this shared binding.
    """

    plugin_id: str
    namespace: str
    manifest: PluginManifest
    scope: Scope
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


HOST_TOOL_TURN: Key[Callable[[], ToolTurn]] = Key("host.tool_turn")
"""The ``tool_turn`` capability: the tool turn running in the current task."""

HOST_CHANNELS: Key[PluginContributionService[ChannelsCapability, Channel]] = Key(
    "host.channels"
)
"""The ``channels`` capability: transports plugins contribute (``core.channels``)."""


# Deliberately accounts-only, not a generic "generation lifecycle" protocol:
# accounts is the only core service with per-generation publish/drop, and P4
# moves publishing and dropping out of the kernel altogether (#903).
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

HOST_SESSIONS: Key[PluginSessions] = Key("host.sessions")
"""The ``sessions`` capability over the host ``SessionManager`` (``session``)."""

HOST_SESSION_MANAGER: Key[SessionUndo] = Key("host.session_manager")
"""The ``session_manager`` capability: the host ``SessionManager`` itself."""

HOST_ROLES: Key[Roles] = Key("host.roles")
"""The ``roles`` capability over the canonical ``RoleStore`` (``core.roles``)."""

HOST_MODELS: Key[RoleModels] = Key("host.models")
"""The ``models`` capability over the ``RoleRuntimeRegistry`` (``core.roles``)."""

HOST_WORKSPACE: Key[Path] = Key("host.workspace")
"""The ``workspace`` capability: the host workspace directory, passed through."""

HOST_HTTP: Key[HttpClient] = Key("host.http")
"""The ``http`` capability: the host's shared external HTTP requester."""


@dataclass(frozen=True)
class Nullable[T]:
    """A provided value that may legitimately be None (``CoreCapability.nullable``).

    The kernel's ``get`` answers None both for a key nobody provided and for a
    provided None; boxing the value keeps "provided" observable, so a missing
    provide still fails instead of reaching the plugin as None.
    """

    value: T | None


HOST_MEMORY_ENGINE: Key[Nullable[MemoryEngine]] = Key("host.memory_engine")
"""The ``memory_engine`` capability: the generation's engine, None when memory is off."""

HOST_PROCESS_RESOURCES: Key[PluginCapabilityBinder[PluginProcessResources]] = Key(
    "host.process_resources"
)
"""The ``process_resources`` capability: process-owned resources (``plugin_host``)."""

HOST_LIGHT_PROVIDER: Key[ChatProvider] = Key("host.light_provider")
"""The ``light_provider`` capability: the host's light chat provider."""

HOST_LIGHT_MODEL: Key[str] = Key("host.light_model")
"""The ``light_model`` capability: the model name to use with ``light_provider``."""

HOST_SCENE_OBSERVATIONS: Key[PluginCapabilityBinder[SceneObservations]] = Key(
    "host.scene_observations"
)
"""The ``scene_observations`` capability over the shared demand (``core.scene``)."""

HOST_MEMORY: Key[MemoryCapability] = Key("host.memory")
"""The ``memory`` capability: the memory plugin's surface (``bootstrap.memory_capabilities``)."""

HOST_PROCESSES: Key[Processes] = Key("host.processes")
"""The ``processes`` capability: host-owned native processes (``infra.process``)."""

HOST_RESOURCES: Key[Resources] = Key("host.resources")
"""The ``resources`` capability: host-distributed resources (``bootstrap.plugin_capability``)."""

HOST_EXTERNAL_TURNS: Key[ExternalTurns] = Key("host.external_turns")
"""The ``external_turns`` capability (``conversation``)."""

HOST_BACKGROUND_RESULTS: Key[BackgroundResults] = Key("host.background_results")
"""The ``background_results`` capability (``conversation``)."""

HOST_BACKGROUND: Key[PluginCapabilityBinder[BackgroundTasks]] = Key("host.background")
"""The ``background`` capability: plugin-scoped tasks (``core.common``)."""

HOST_EVENTS: Key[PluginCapabilityBinder[EventsCapability]] = Key("host.events")
"""The ``events`` capability: a plugin-scoped view of the event bus (``bus``)."""

HOST_RPC: Key[PluginCapabilityBinder[RpcCapability]] = Key("host.rpc")
"""The ``rpc`` capability: bridge-callable plugin methods (``desktop_bridge``)."""

# The policy type (``desktop_bridge.method_policy.MethodPolicy``) is a host
# module this layer may not import; the kernel only binds and withdraws.
HOST_BRIDGE: Key[PluginRpcRegistry[Any]] = Key("host.bridge")
"""The generation's plugin RPC registry, created by bootstrap (``desktop_bridge``).

Not a capability row: the kernel binds renderer communication to it and the
``services`` capability uses its service registry, so each generation requires
it when it is constructed.
"""

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
    instance itself is the capability, shared by every plugin. ``nullable``
    marks a capability for which None is a valid host state: its key provides
    a ``Nullable`` box and the plugin gets the boxed value, None included.
    """

    key: Key[Any]
    per_plugin: bool = False
    nullable: bool = False


# v2 capability name (which is also the plugin context argument it fills) ->
# the core key behind it. The capabilities missing here are kernel-native: the
# assembly layer builds them itself (config, dependencies, runtime, kv, storage,
# services).
CORE_CAPABILITIES: Mapping[str, CoreCapability] = {
    "diagnostics": CoreCapability(HOST_DIAGNOSTICS),
    "tools": CoreCapability(HOST_TOOLS, per_plugin=True),
    "tool_turn": CoreCapability(HOST_TOOL_TURN),
    "channels": CoreCapability(HOST_CHANNELS, per_plugin=True),
    "accounts": CoreCapability(HOST_ACCOUNTS, per_plugin=True),
    "avatars": CoreCapability(HOST_AVATARS, per_plugin=True),
    "sessions": CoreCapability(HOST_SESSIONS),
    "session_manager": CoreCapability(HOST_SESSION_MANAGER),
    "roles": CoreCapability(HOST_ROLES),
    "models": CoreCapability(HOST_MODELS),
    "light_provider": CoreCapability(HOST_LIGHT_PROVIDER),
    "light_model": CoreCapability(HOST_LIGHT_MODEL),
    "scene_observations": CoreCapability(HOST_SCENE_OBSERVATIONS, per_plugin=True),
    "memory": CoreCapability(HOST_MEMORY),
    "processes": CoreCapability(HOST_PROCESSES),
    "resources": CoreCapability(HOST_RESOURCES),
    "external_turns": CoreCapability(HOST_EXTERNAL_TURNS),
    "background_results": CoreCapability(HOST_BACKGROUND_RESULTS),
    "background": CoreCapability(HOST_BACKGROUND, per_plugin=True),
    "events": CoreCapability(HOST_EVENTS, per_plugin=True),
    "rpc": CoreCapability(HOST_RPC, per_plugin=True),
    "workspace": CoreCapability(HOST_WORKSPACE),
    "http": CoreCapability(HOST_HTTP),
    "memory_engine": CoreCapability(HOST_MEMORY_ENGINE, nullable=True),
    "process_resources": CoreCapability(HOST_PROCESS_RESOURCES, per_plugin=True),
}


def bind_core_capabilities(
    capabilities: Iterable[str],
    provided: Callable[[Key[Any]], object],
    binding: PluginBinding,
) -> dict[str, Any]:
    """Plugin context arguments for the declared capabilities the core provides.

    ``provided`` looks a key up in the kernel (``Kernel.get``). A declared
    capability whose key nobody provides fails before setup, like a missing
    host service; that includes a ``nullable`` row, whose provided box may
    hold None.
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
        if row.nullable:
            arguments[capability] = value.value
        elif row.per_plugin:
            arguments[capability] = value.for_plugin(binding)
        else:
            arguments[capability] = value
    return arguments


def required_core_key[T](provided: Callable[[Key[T]], T | None], key: Key[T]) -> T:
    """The provider of a key the assembly layer cannot run without."""
    if (value := provided(key)) is None:
        raise HostServiceUnavailable(f"宿主未提供核心服务 {key.name}")
    return value
