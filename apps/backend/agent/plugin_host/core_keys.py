"""Host assembly keys and the per-plugin view a ``require`` returns.

Core modules provide public keys (``shiori_sdk.core``) before any plugin
starts. A binder is stored as itself; ``PluginRuntimeContext.require`` calls
``for_plugin`` so the plugin sees its own view. Host-only wiring is supplied
as explicit constructor arguments; no manifest may name a ``host.`` key.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, Protocol

from shiori_sdk.kernel import Key, Scope
from shiori_sdk.runtime import HostServiceUnavailable

from agent.plugin_host.call_gate import PluginCallGate
from agent.plugin_host.manifest import PluginManifest
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


class PluginViewBinder[T](Protocol):
    """A core service that hands each plugin its own view."""

    def for_plugin(self, binding: PluginBinding) -> T:
        """The object for the plugin ``binding`` describes."""
        ...


class CoreProvide(Protocol):
    """What a core module is given to publish its services: ``Kernel.provide``."""

    def __call__[T](self, key: Key[T], impl: T) -> None: ...


CoreModule = Callable[[CoreProvide], None]
"""Provides one core module's keys; raising aborts startup (§8.5)."""


class HostBuilt:
    """Marker for a public key the host builds per plugin during setup.

    ``config``, ``kv``, ``dependencies`` and ``runtime`` do not
    exist until the assembly layer constructs that plugin's context. The kernel
    still needs a provider so planning does not block a plugin that injects one. ``PluginRuntimeContext.require``
    replaces this marker with the plugin's object. It is not a service.

    Remove it once kernel planning can tell a host-built per-plugin key from
    a missing provider; until then a plugin injecting one would be BLOCKED.
    No phase owns that change yet.
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
        "background",
        "events",
        "rpc",
        "services",
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
)


def required_core_key[T](provided: Callable[[Key[T]], T | None], key: Key[T]) -> T:
    """The provider of a key the assembly layer cannot run without."""
    if (value := provided(key)) is None:
        raise HostServiceUnavailable(f"宿主未提供核心服务 {key.name}")
    return value
