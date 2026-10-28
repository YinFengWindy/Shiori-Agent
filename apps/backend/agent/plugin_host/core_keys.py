"""Host assembly keys and the per-plugin view a ``require`` returns.

Core modules provide public keys (``shiori_sdk.core``) before any plugin
starts. A binder is stored as itself; ``PluginRuntimeContext.require`` calls
``for_plugin`` so the plugin sees its own view. ``host.bridge`` and
``host.config_references`` are host-internal and are not service keys plugins
inject. api: 4 manifests cannot name a ``host.`` key. api: 2 may still list
one until P4-5 rejects non-``api: 4`` packages.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable, Sequence
from dataclasses import dataclass
from typing import Any, Protocol

from shiori_sdk.accounts.capability import AccountsCapability
from shiori_sdk.kernel import Key, Scope
from shiori_sdk.runtime import HostServiceUnavailable

from agent.plugin_host.call_gate import PluginCallGate
from agent.plugin_host.manifest import PluginManifest
from agent.plugin_host.rpc import PluginRpcRegistry
from shiori_sdk.core import services


@dataclass(frozen=True)
class PluginBinding:
    """One plugin activation, for the binders that scope a service to it.

    ``scope`` releases what the service registered when the plugin stops,
    and ``calls`` admits or refuses calls into the plugin. ``namespace`` is the
    kernel generation's import namespace; ``manifest`` is the plugin's parsed
    manifest, for the static declarations a service checks against.

    Only the plugin's identity and static declarations (manifest), its scope
    and its call gate belong here. Data one service alone needs stays with
    that service, never in this shared binding.
    """

    plugin_id: str
    namespace: str
    manifest: PluginManifest
    scope: Scope
    calls: PluginCallGate


class PluginCapabilityBinder[T](Protocol):
    """A core service that hands each plugin its own view."""

    def for_plugin(self, binding: PluginBinding) -> T:
        """The object for the plugin ``binding`` describes."""
        ...


class ActiveContributions[T](Protocol):
    """Objects plugins contributed, read back for the active plugins only."""

    def active(self, plugin_ids: Iterable[str]) -> Sequence[T]:
        """The contributions of ``plugin_ids`` (kernel order), in that order."""
        ...


class PluginContributionService[C, T](
    PluginCapabilityBinder[C], ActiveContributions[T], Protocol
):
    """A per-plugin view ``C`` whose contributions ``T`` the host aggregates.

    Each plugin adds through its own ``for_plugin`` view; consumers read the
    active plugins' contributions with ``active``.
    ``capabilities.ContributionsByPlugin`` is the shared storage behind it.
    """


class CoreProvide(Protocol):
    """What a core module is given to publish its services: ``Kernel.provide``."""

    def __call__[T](self, key: Key[T], impl: T) -> None: ...


CoreModule = Callable[[CoreProvide], None]
"""Provides one core module's keys; raising aborts startup (§8.5)."""


# Deliberately accounts-only, not a generic "generation lifecycle" protocol:
# accounts is the only core service with per-generation publish/drop.
class GenerationAccounts(PluginCapabilityBinder[AccountsCapability], Protocol):
    """One kernel generation's account index, stored under ``ACCOUNTS``.

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


# The policy type (``desktop_bridge.method_policy.MethodPolicy``) is a host
# module this layer may not import; the kernel only binds and withdraws.
HOST_BRIDGE: Key[PluginRpcRegistry[Any]] = Key("host.bridge")
"""The generation's plugin RPC registry, created by bootstrap (``desktop_bridge``).

Not a service plugins inject: the kernel binds renderer communication to it
and the ``services`` key uses its service registry, so each generation
requires it when it is constructed.
"""

HOST_CONFIG_REFERENCES: Key[Callable[[str], str]] = Key("host.config_references")
"""Expands ``${NAME}`` references for ``config.resolve_reference``.

Not a service plugins inject: the assembly layer itself needs it for every
plugin's ``config``, so each generation requires it when it is constructed.
"""


class HostBuilt:
    """Marker for a public key the host builds per plugin during setup.

    ``config``, ``kv``, ``dependencies``, ``runtime``, ``services`` and
    ``storage`` do not exist until the assembly layer constructs that
    plugin's context. The kernel still needs a provider so planning does
    not block a plugin that injects one. ``PluginRuntimeContext.require``
    replaces this marker with the plugin's object. It is not a service.
    """


# Public names whose provider is a binder: ``require`` returns
# ``provider.for_plugin(binding)``, and the same view on every call (the
# events view's ``off`` only sees subscriptions on that view).
PER_PLUGIN_PUBLIC_KEYS = frozenset(
    {
        "tools",
        "channels",
        "accounts",
        "avatars",
        "scene_observations",
        "background",
        "events",
        "rpc",
        "process_resources",
    }
)

# The public keys ``HostBuilt`` stands in for; bootstrap provides the marker
# under each.
HOST_BUILT_KEYS: tuple[Key[Any], ...] = (
    services.CONFIG,
    services.KV,
    services.DEPENDENCIES,
    services.RUNTIME,
    services.SERVICES,
    services.STORAGE,
)


def required_core_key[T](provided: Callable[[Key[T]], T | None], key: Key[T]) -> T:
    """The provider of a key the assembly layer cannot run without."""
    if (value := provided(key)) is None:
        raise HostServiceUnavailable(f"宿主未提供核心服务 {key.name}")
    return value
