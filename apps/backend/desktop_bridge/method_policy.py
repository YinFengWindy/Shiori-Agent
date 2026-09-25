"""One declarative policy record per bridge method.

Both request scheduling (`request_dispatcher`) and endpoint routing
(`desktop_bridge.runtime.service`) read this table, so adding a method
means declaring its concurrency lane, reload admission and cancellation
ownership in exactly one place. Unregistered methods keep the historical
conservative defaults: serial mutation lane, subject to reload admission,
served by the current generation.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from enum import Enum
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    # Only for type annotations: avoids pulling desktop_bridge's dependency
    # chain into the core plugin runtime at import time (mirrors the same
    # discipline agent.plugin_host.rpc already applies in the other direction).
    from agent.plugin_host.rpc import PluginRpcRegistry


class Concurrency(Enum):
    """Which dispatcher lane runs the request."""

    READ_ONLY = "read_only"
    INTEGRATION = "integration"
    MUTATION = "mutation"
    # The settings transaction owns its serial lock; scheduling it through a
    # shared lane would starve health checks and cancellation while it drains.
    SETTINGS_APPLY = "settings_apply"
    # Renderer rendezvous must leave capacity for callback RPCs and their replies.
    PLUGIN_TRANSPORT = "plugin_transport"


class Handler(Enum):
    """Which endpoint branch of ReloadableDesktopService serves the request."""

    GENERATION = "generation"
    SETTINGS = "settings"
    ROLE_TASKS = "role_tasks"
    PLUGIN_CONFIG = "plugin_config"
    PLUGIN_MANAGEMENT = "plugin_management"
    DESKTOP_PRESENCE = "desktop_presence"


class OwnerRouting(Enum):
    """How the endpoint picks the runtime generation that serves the request."""

    CURRENT = "current"
    BUSY_CHAT_SESSION = "busy_chat_session"
    BUSY_VOICE_TURN = "busy_voice_turn"
    BUSY_VOICE_SYNTHESIS = "busy_voice_synthesis"


@dataclass(frozen=True)
class MethodPolicy:
    concurrency: Concurrency = Concurrency.MUTATION
    admission_exempt: bool = False
    owner_routing: OwnerRouting = OwnerRouting.CURRENT
    handler: Handler = Handler.GENERATION


_DEFAULT_POLICY = MethodPolicy()

METHOD_POLICIES: dict[str, MethodPolicy] = {
    **{
        method: MethodPolicy(
            concurrency=Concurrency.MUTATION,
            admission_exempt=True,
            handler=Handler.PLUGIN_MANAGEMENT,
        )
        for method in (
            "plugins.install.preview",
            "plugins.install.confirm",
            "plugins.install.cancel",
            "plugins.uninstall",
        )
    },
    "health": MethodPolicy(concurrency=Concurrency.READ_ONLY, admission_exempt=True),
    "runtime.status": MethodPolicy(
        concurrency=Concurrency.READ_ONLY,
        admission_exempt=True,
        handler=Handler.SETTINGS,
    ),
    "runtime.apply": MethodPolicy(
        concurrency=Concurrency.SETTINGS_APPLY,
        admission_exempt=True,
        handler=Handler.SETTINGS,
    ),
    "plugin.config.get": MethodPolicy(
        concurrency=Concurrency.READ_ONLY,
        admission_exempt=True,
        handler=Handler.PLUGIN_CONFIG,
    ),
    "plugin.config.set": MethodPolicy(
        # 写入复用设置事务自己的串行锁，语义与 runtime.apply 一致
        concurrency=Concurrency.SETTINGS_APPLY,
        admission_exempt=True,
        handler=Handler.PLUGIN_CONFIG,
    ),
    "plugins.list": MethodPolicy(
        concurrency=Concurrency.READ_ONLY,
        admission_exempt=True,
        handler=Handler.PLUGIN_MANAGEMENT,
    ),
    "plugins.setEnabled": MethodPolicy(
        # 同样复用设置事务自己的串行锁：启停一律走一次完整的生成代切换
        concurrency=Concurrency.SETTINGS_APPLY,
        admission_exempt=True,
        handler=Handler.PLUGIN_MANAGEMENT,
    ),
    "channels.list": MethodPolicy(
        # Static declarations plus the published generation's channel state.
        concurrency=Concurrency.READ_ONLY,
        admission_exempt=True,
        handler=Handler.PLUGIN_MANAGEMENT,
    ),
    "plugins.trust": MethodPolicy(
        concurrency=Concurrency.MUTATION,
        admission_exempt=True,
        handler=Handler.PLUGIN_MANAGEMENT,
    ),
    "plugins.activation.report": MethodPolicy(
        # A renderer's own load-outcome report; never gated by the settings
        # transaction lock and never blocked by a reload in progress, since
        # it targets whatever generation is current when it arrives (#262).
        concurrency=Concurrency.MUTATION,
        admission_exempt=True,
        handler=Handler.PLUGIN_MANAGEMENT,
    ),
    "desktop.presence.report": MethodPolicy(
        # A single in-memory overwrite that shares no state with the serial
        # write lane; it must not queue behind long mutations or a reload.
        concurrency=Concurrency.READ_ONLY,
        admission_exempt=True,
        handler=Handler.DESKTOP_PRESENCE,
    ),
    # A network probe of an unsaved draft: it must not hold the serial
    # mutation lane (or a read slot) for up to its 20s deadline.
    "models.test": MethodPolicy(concurrency=Concurrency.INTEGRATION),
    "roles.tasks.list": MethodPolicy(
        concurrency=Concurrency.READ_ONLY,
        admission_exempt=True,
        handler=Handler.ROLE_TASKS,
    ),
    "roles.tasks.cancel": MethodPolicy(
        admission_exempt=True, handler=Handler.ROLE_TASKS
    ),
    "roles.list": MethodPolicy(
        concurrency=Concurrency.READ_ONLY, admission_exempt=True
    ),
    "session.messagesPage": MethodPolicy(
        concurrency=Concurrency.READ_ONLY, admission_exempt=True
    ),
    "session.messagesAround": MethodPolicy(concurrency=Concurrency.READ_ONLY),
    "session.search": MethodPolicy(concurrency=Concurrency.READ_ONLY),
    "session.imageHistory": MethodPolicy(concurrency=Concurrency.READ_ONLY),
    "voice.synthesize": MethodPolicy(concurrency=Concurrency.INTEGRATION),
    "voice.synthesize.cancel": MethodPolicy(
        concurrency=Concurrency.INTEGRATION,
        admission_exempt=True,
        owner_routing=OwnerRouting.BUSY_VOICE_SYNTHESIS,
    ),
    "chat.cancel": MethodPolicy(
        admission_exempt=True,
        owner_routing=OwnerRouting.BUSY_CHAT_SESSION,
    ),
    "voice.turn.cancel": MethodPolicy(
        admission_exempt=True,
        owner_routing=OwnerRouting.BUSY_VOICE_TURN,
    ),
}


def method_policy(method: str) -> MethodPolicy:
    """Returns the declared policy, or the conservative default for new methods."""
    if method.startswith("plugins.communication."):
        return MethodPolicy(
            concurrency=Concurrency.PLUGIN_TRANSPORT,
            admission_exempt=method.endswith((".close", ".reply", ".disconnect")),
        )
    return METHOD_POLICIES.get(method, _DEFAULT_POLICY)


# ``plugin.<id>.<method>`` methods are not in the static table above: their
# policy is whatever the owning plugin declared via ``ctx.rpc.register``.
# ``plugin.config.*`` is excluded from that because it is served directly by
# ``ReloadableDesktopService`` (declared statically above), never through a
# plugin-declared RPC registration.
_PLUGIN_METHOD_PREFIX = "plugin."
_PLUGIN_CONFIG_METHOD_PREFIX = "plugin.config."


def resolve_plugin_method_policy(
    method: str,
    registry_provider: "Callable[[], PluginRpcRegistry | None]",
) -> MethodPolicy:
    """Resolves dispatcher policy for one request, consulting a plugin RPC registry.

    Shared by ``DesktopBridgeService`` (single generation) and
    ``ReloadableDesktopService`` (leases the active generation's registry)
    so the ``plugin.`` prefix rule is declared in exactly one place.

    ``registry_provider`` is only called for ``plugin.<id>.<method>``: most
    requests never touch a plugin registry at all, and ``ReloadableDesktopService``
    only has one to offer once it has resolved the active generation's kernel,
    which callers should not have to do for every request regardless of method.
    """
    if method.startswith(_PLUGIN_METHOD_PREFIX) and not method.startswith(
        _PLUGIN_CONFIG_METHOD_PREFIX,
    ):
        registry = registry_provider()
        if registry is not None:
            policy = registry.policy_for(method)
            if policy is not None:
                return policy
        return MethodPolicy()
    return method_policy(method)
