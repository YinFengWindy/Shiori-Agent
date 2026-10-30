"""The core modules that provide their services to the plugin kernel (#901 P2).

Each entry publishes one core module's keys before any plugin is planned. A
core module whose provide raises aborts startup (§8.5); plugins only ever fail
on their own. Adapters that turn a core service into a v2 capability live
here, since bootstrap already imports both the core and the assembly layer.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, cast

from agent.config import resolve_config_reference
from infra.process.resources import (
    PluginProcessResourceAttachments,
    ProcessResourceOwner,
)
from agent.plugin_host.rpc import PluginRpcRegistry
from agent.provider import LLMProvider
from agent.plugin_host.core_keys import (
    HOST_BRIDGE,
    HOST_BUILT_KEYS,
    HOST_CONFIG_REFERENCES,
    CoreModule,
    CoreProvide,
    HostBuilt,
)
from agent.tools.plugin_capability import PluginTools
from agent.tools.registry import ToolRegistry
from agent.tools.turn_scope import current_tool_turn
from bootstrap.memory_capabilities import HostMemoryCapability
from bootstrap.plugin_capability import HostResources
from bus.event_bus import EventBus
from bus.plugin_capability import PluginEvents
from core.accounts.plugin_capability import PluginAccounts
from core.channels.plugin_capability import PluginAvatars, PluginChannels
from core.common.crash_reporting import HostCrashReporting
from core.common.plugin_capability import PluginBackground
from core.roles.plugin_capability import HostRoleModels, HostRoles
from core.roles.role_runtime import RoleRuntimeRegistry
from core.roles.store import RoleStore
from agent.tools.mcp_registration import HostMcpToolRegistration
from core.roles.affection_host import HostAffectionSources
from core.scene.host import HostSceneAdapter
from desktop_bridge.method_policy import MethodPolicy
from desktop_bridge.plugin_capability import PluginRpc
from desktop_bridge.session_presenter import DesktopSessionPresenter
from infra.process.plugin_capability import HostProcesses
from session.manager import SessionManager
from session.plugin_capability import HostSessions
from shiori_sdk.background_results import BackgroundResults
from shiori_sdk.commands import CommandRegistry
from shiori_sdk.core.affection_host import AFFECTION_HOST
from shiori_sdk.core.conversation import COMMANDS
from shiori_sdk.core.mcp_tools import MCP_TOOLS
from shiori_sdk.core.scene import SCENE_HOST
from shiori_sdk.core.crash_reporting import CRASH_REPORTING
from shiori_sdk.core.models import MAIN_MODEL, MAIN_PROVIDER
from shiori_sdk.core.services import (
    ACCOUNTS,
    AVATARS,
    BACKGROUND,
    BACKGROUND_RESULTS,
    CHANNELS,
    EVENTS,
    EXTERNAL_TURNS,
    HTTP,
    LIGHT_MODEL,
    LIGHT_PROVIDER,
    MEMORY,
    MODELS,
    PROCESS_RESOURCES,
    PROCESSES,
    RESOURCES,
    ROLES,
    RPC,
    SESSION_STORE,
    TOOL_TURN,
    TOOLS,
    WORKSPACE,
)
from shiori_sdk.core.sessions import SESSIONS, Sessions
from shiori_sdk.kernel import Key
from shiori_sdk.external_turns import ExternalTurns
from shiori_sdk.http import HttpClient
from shiori_sdk.models import RoleModels
from shiori_sdk.processes import Processes, Resources
from shiori_sdk.roles import Roles
from shiori_sdk.sessions import PluginSessions


@dataclass(frozen=True, kw_only=True)
class PluginCoreInputs:
    """What one runtime generation's core modules provide to its plugin kernel.

    ``plugin_dirs`` are the generation's plugin discovery roots: every plugin
    is a directory directly under one, which is how crash reporting attributes
    a traceback frame to ``plugins/<directory>/...``. ``event_bus`` is the
    generation's event bus and ``rpc`` its plugin RPC registry, created over
    that bus. ``scene_followup`` is the host strategy flag the scene plugin
    reads through ``SCENE_HOST``; the plugin does not own that flag.

    The rest back capabilities; when one is None (host tests), a plugin
    declaring a capability over it fails before setup:

    - ``tools``: the generation's tool registry.
    - ``role_store``: the canonical role store, behind ``roles``, ``accounts``
      and ``avatars`` (its account index and avatar cache) and, with the
      ``workspace``, ``memory``.
    - ``session_manager``: the ``sessions`` socket (``SESSIONS``) and, with
      the ``workspace`` holding session media, session metadata
      (``SESSION_STORE``), whose payloads the desktop presenter projects.
    - ``role_runtime_registry``: ``models``.
    - ``provider`` / ``model``: the main chat pair, provided as
      ``MAIN_PROVIDER`` and ``MAIN_MODEL``. None means this generation has no
      chat model; a plugin that injects either is blocked.
    - ``light_provider`` / ``light_model``: the plugins' light model.
    - ``external_turns`` / ``background_results``: the conversation services,
      built over the generation's agent loop.
    - ``workspace`` and ``http``: passed through as they are.
    - ``process_resources``: the process-level owner whose per-generation
      attachments plugins get.
    """

    plugin_dirs: tuple[Path, ...]
    event_bus: EventBus
    rpc: PluginRpcRegistry[MethodPolicy]
    scene_followup: bool = False
    # The same directory as ``PluginGenerationSettings.workspace``: there the
    # kernel's trust store, execution identity and KV root; here the
    # ``workspace``, ``memory`` and ``sessions`` capabilities.
    workspace: Path | None
    tools: ToolRegistry | None
    role_store: RoleStore | None
    session_manager: SessionManager | None
    presence: Any | None = None
    role_runtime_registry: RoleRuntimeRegistry | None
    provider: LLMProvider | None
    model: str | None
    light_provider: LLMProvider | None
    light_model: str | None
    external_turns: ExternalTurns | None
    background_results: BackgroundResults | None
    http: HttpClient | None
    # The same owner as ``PluginGenerationSettings.process_resources``: there
    # the kernel publishes and retains the generation's attachments; here
    # each plugin gets its attachment (``process_resources``).
    process_resources: ProcessResourceOwner | None


def _publish(provide: CoreProvide, key: object, impl: object) -> None:
    """Publishes ``impl`` under a public key plugins inject.

    A binder is stored as itself. ``PluginRuntimeContext.require`` calls
    ``for_plugin`` before the plugin sees it, so the key's type is the view
    the plugin calls, not the binder. ``HostBuilt`` is the stand-in for a
    key built per plugin during setup. ``key`` is ``object`` because ``Key``
    is invariant and the stored binder is not the view type.
    """
    provide(cast(Key[Any], key), cast(Any, impl))


def plugin_core_modules(inputs: PluginCoreInputs) -> tuple[CoreModule, ...]:
    """The core provide list, in provide order, for one runtime generation."""
    roots = [("plugins", directory.resolve()) for directory in inputs.plugin_dirs]

    def provide_plugin_locals(provide: CoreProvide) -> None:
        """Keys the assembly layer builds per plugin (config, kv, and the rest)."""
        marker = HostBuilt()
        for key in HOST_BUILT_KEYS:
            _publish(provide, key, marker)

    def provide_crash_reporting(provide: CoreProvide) -> None:
        """``CRASH_REPORTING``: process hooks plus session and frame attribution."""
        provide(CRASH_REPORTING, HostCrashReporting(roots))

    def provide_config_references(provide: CoreProvide) -> None:
        """The host's ``${NAME}`` expansion behind ``config.resolve_reference``."""
        provide(HOST_CONFIG_REFERENCES, resolve_config_reference)

    def provide_tools(provide: CoreProvide) -> None:
        """Plugin tools and the current tool turn (``agent.tools``)."""
        if inputs.tools is not None:
            _publish(provide, TOOLS, PluginTools(inputs.tools))
        provide(TOOL_TURN, current_tool_turn)

    def provide_channels(provide: CoreProvide) -> None:
        """Plugin channels, and the accounts and avatars they serve (``core.channels``)."""
        _publish(provide, CHANNELS, PluginChannels())
        if inputs.role_store is not None:
            _publish(provide, ACCOUNTS, PluginAccounts(inputs.role_store.accounts))
            _publish(provide, AVATARS, PluginAvatars(inputs.role_store.avatars))

    def provide_sessions(provide: CoreProvide) -> None:
        """The sessions socket and session media (``session``)."""
        if inputs.session_manager is None:
            return
        # Typed as the plugin contract, so pyright checks the host implementation.
        sessions_api: Sessions = inputs.session_manager
        provide(SESSIONS, sessions_api)
        if inputs.workspace is not None:
            presenter = DesktopSessionPresenter(None)
            # Typed as the plugin contract, so pyright checks the host implementation.
            sessions: PluginSessions = HostSessions(
                inputs.session_manager, inputs.workspace, presenter
            )
            provide(SESSION_STORE, sessions)

    def provide_roles(provide: CoreProvide) -> None:
        """Roles, their models, and the main and light chat pairs (``core.roles``)."""
        # Typed as the plugin contracts, so pyright checks the host implementations.
        if inputs.role_store is not None:
            roles: Roles = HostRoles(inputs.role_store)
            provide(ROLES, roles)
        if inputs.role_runtime_registry is not None:
            models: RoleModels = HostRoleModels(inputs.role_runtime_registry)
            provide(MODELS, models)
        if inputs.provider is not None:
            provide(MAIN_PROVIDER, inputs.provider)
        if inputs.model is not None:
            provide(MAIN_MODEL, inputs.model)
        if inputs.light_provider is not None:
            provide(LIGHT_PROVIDER, inputs.light_provider)
        if inputs.light_model is not None:
            provide(LIGHT_MODEL, inputs.light_model)

    def provide_scene(provide: CoreProvide) -> None:
        """Host facts for the scene plugin. The plugin provides ``SCENE``."""
        if (
            inputs.workspace is not None
            and inputs.role_store is not None
            and inputs.session_manager is not None
        ):
            provide(
                SCENE_HOST,
                HostSceneAdapter(
                    workspace=inputs.workspace,
                    roles=inputs.role_store,
                    sessions=inputs.session_manager,
                    scene_followup=inputs.scene_followup,
                ),
            )

    def provide_affection(provide: CoreProvide) -> None:
        """Host facts for the affection plugin. The plugin provides ``AFFECTION``."""
        if (
            inputs.workspace is not None
            and inputs.role_store is not None
            and inputs.session_manager is not None
        ):
            provide(
                AFFECTION_HOST,
                HostAffectionSources(
                    workspace=inputs.workspace,
                    role_store=inputs.role_store,
                    session_manager=inputs.session_manager,
                    presence=inputs.presence,
                    role_runtime=inputs.role_runtime_registry,
                ),
            )

    def provide_mcp_tools(provide: CoreProvide) -> None:
        """Registration of dynamic MCP tools. The mcp plugin calls this."""
        if inputs.tools is not None:
            provide(MCP_TOOLS, HostMcpToolRegistration(inputs.tools))

    def provide_memory(provide: CoreProvide) -> None:
        """The memory plugin's surface (``bootstrap.memory_capabilities``).

        The engine itself is provided by a plugin as ``MEMORY_ENGINE``.
        """
        if inputs.workspace is not None and inputs.role_store is not None:
            provide(MEMORY, HostMemoryCapability(inputs.workspace, inputs.role_store))

    def provide_processes(provide: CoreProvide) -> None:
        """Native processes, process-owned resources and distributed resources."""
        # Typed as the plugin contracts, so pyright checks the host implementations.
        processes: Processes = HostProcesses()
        provide(PROCESSES, processes)
        if inputs.process_resources is not None:
            _publish(
                provide,
                PROCESS_RESOURCES,
                PluginProcessResourceAttachments(inputs.process_resources),
            )
        resources: Resources = HostResources()
        provide(RESOURCES, resources)

    def provide_conversation(provide: CoreProvide) -> None:
        """External turns, background results and ``COMMANDS`` (``conversation``)."""
        if inputs.external_turns is not None:
            provide(EXTERNAL_TURNS, inputs.external_turns)
        if inputs.background_results is not None:
            provide(BACKGROUND_RESULTS, inputs.background_results)
        provide(COMMANDS, CommandRegistry())

    def provide_background(provide: CoreProvide) -> None:
        """Plugin-scoped background tasks (``core.common``)."""
        _publish(provide, BACKGROUND, PluginBackground())

    def provide_bridge(provide: CoreProvide) -> None:
        """The plugin RPC registry and the ``rpc`` capability over it (bridge)."""
        provide(HOST_BRIDGE, inputs.rpc)
        _publish(provide, RPC, PluginRpc(inputs.rpc, inputs.event_bus))

    def provide_events(provide: CoreProvide) -> None:
        """Plugin-scoped views of the event bus (``bus``)."""
        _publish(provide, EVENTS, PluginEvents(inputs.event_bus))

    def provide_host_passthrough(provide: CoreProvide) -> None:
        """The workspace directory and the shared external HTTP requester."""
        if inputs.workspace is not None:
            provide(WORKSPACE, inputs.workspace)
        if inputs.http is not None:
            provide(HTTP, inputs.http)

    return (
        provide_plugin_locals,
        provide_bridge,
        provide_events,
        provide_crash_reporting,
        provide_config_references,
        provide_tools,
        provide_channels,
        provide_sessions,
        provide_roles,
        provide_scene,
        provide_affection,
        provide_mcp_tools,
        provide_memory,
        provide_processes,
        provide_conversation,
        provide_background,
        provide_host_passthrough,
    )
