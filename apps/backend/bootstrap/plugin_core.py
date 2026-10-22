"""The core modules that provide their services to the plugin kernel (#901 P2).

Each entry publishes one core module's keys before any plugin is planned. A
core module whose provide raises aborts startup (§8.5); plugins only ever fail
on their own. Adapters that turn a core service into a v2 capability live
here, since bootstrap already imports both the core and the assembly layer.
"""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path

from agent.config import resolve_config_reference
from agent.core.proactive_turn.plugin_capability import PluginProactiveGates
from agent.plugin_host.rpc import PluginRpcRegistry
from agent.provider import LLMProvider
from agent.plugin_host.core_keys import (
    HOST_ACCOUNTS,
    HOST_AVATARS,
    HOST_BACKGROUND,
    HOST_BACKGROUND_RESULTS,
    HOST_BOT_COMMANDS,
    HOST_BRIDGE,
    HOST_CHANNELS,
    HOST_CONFIG_REFERENCES,
    HOST_DIAGNOSTICS,
    HOST_EVENTS,
    HOST_EXTERNAL_TURNS,
    HOST_LIGHT_MODEL,
    HOST_LIGHT_PROVIDER,
    HOST_MEMORY,
    HOST_MODELS,
    HOST_PROACTIVE_GATES,
    HOST_PROCESSES,
    HOST_RESOURCES,
    HOST_RPC,
    HOST_ROLE_RUNTIME_REGISTRY,
    HOST_ROLES,
    HOST_SCENE_OBSERVATIONS,
    HOST_SESSION_MANAGER,
    HOST_SESSIONS,
    HOST_TOOL_HOOKS,
    HOST_TOOL_TURN,
    HOST_TOOLS,
    CoreModule,
    CoreProvide,
)
from agent.tool_hooks.plugin_capability import PluginToolHooks
from agent.tools.plugin_capability import PluginTools
from agent.tools.registry import ToolRegistry
from agent.tools.turn_scope import current_tool_turn
from bootstrap.memory_capabilities import HostMemoryCapability
from bootstrap.plugin_capability import HostResources
from bus.event_bus import EventBus
from bus.plugin_capability import PluginEvents
from conversation.plugin_capability import PluginBotCommands
from core.accounts.plugin_capability import PluginAccounts
from core.channels.plugin_capability import PluginAvatars, PluginChannels
from core.common.diagnostics import HostDiagnostics
from core.common.global_hook_stack import ProcessCrashReporting
from core.common.plugin_capability import PluginBackground
from core.roles.plugin_capability import HostRoleModels, HostRoles
from core.roles.role_runtime import RoleRuntimeRegistry
from core.roles.store import RoleStore
from core.scene.demand import SceneObservationDemand
from core.scene.plugin_capability import PluginSceneObservations
from desktop_bridge.method_policy import MethodPolicy
from desktop_bridge.plugin_capability import PluginRpc
from desktop_bridge.session_presenter import DesktopSessionPresenter
from infra.process.plugin_capability import HostProcesses
from session.manager import SessionManager
from session.plugin_capability import HostPluginSessions
from shiori_sdk.background_results import BackgroundResults
from shiori_sdk.core.crash_reporting import CRASH_REPORTING
from shiori_sdk.external_turns import ExternalTurns
from shiori_sdk.memory.engine import MemoryEngine
from shiori_sdk.processes import Resources


def plugin_core_modules(
    plugin_dirs: Sequence[Path],
    *,
    tools: ToolRegistry | None,
    role_store: RoleStore | None,
    session_manager: SessionManager | None,
    workspace: Path | None,
    relationship_runtime: object,
    role_runtime_registry: RoleRuntimeRegistry | None,
    light_provider: LLMProvider | None,
    light_model: str | None,
    scene_observations: SceneObservationDemand,
    memory_engine: MemoryEngine | None,
    external_turns: ExternalTurns | None,
    background_results: BackgroundResults | None,
    event_bus: EventBus,
    rpc: PluginRpcRegistry[MethodPolicy],
) -> tuple[CoreModule, ...]:
    """The core provide list, in provide order, for one runtime generation.

    ``plugin_dirs`` are the generation's plugin discovery roots: every plugin
    is a directory directly under one, which is how diagnostics attributes a
    traceback frame to ``plugins/<directory>/...``. ``tools`` is the
    generation's tool registry and ``role_store`` the host's canonical role
    store, whose account index and avatar cache back ``accounts`` and
    ``avatars``; without one (host tests) a plugin declaring a capability
    over it fails before setup. ``session_manager`` backs ``session_manager``
    and, with the ``workspace`` holding session media, ``sessions``, whose
    payloads the desktop presenter projects with ``relationship_runtime``.
    ``role_store`` also backs ``roles``, and ``role_runtime_registry`` backs
    ``models`` and its own passthrough; ``light_provider`` and ``light_model``
    are the plugins' light model. ``scene_observations`` is the generation's
    demand registry the scene controller reads. ``memory_engine`` (None when
    memory is disabled) goes into ``memory`` with the workspace and role store.
    ``external_turns`` and ``background_results`` are the generation's
    conversation services, built over its agent loop. ``event_bus`` is the
    generation's event bus and ``rpc`` its plugin RPC registry, created by
    bootstrap over that bus.
    """
    roots = [("plugins", directory.resolve()) for directory in plugin_dirs]

    def provide_diagnostics(provide: CoreProvide) -> None:
        """``CRASH_REPORTING`` and the ``diagnostics`` capability over it (D13b)."""
        crash_reporting = ProcessCrashReporting()
        provide(CRASH_REPORTING, crash_reporting)
        provide(HOST_DIAGNOSTICS, HostDiagnostics(crash_reporting, roots))

    def provide_config_references(provide: CoreProvide) -> None:
        """The host's ``${NAME}`` expansion behind ``config.resolve_reference``."""
        provide(HOST_CONFIG_REFERENCES, resolve_config_reference)

    def provide_tools(provide: CoreProvide) -> None:
        """Plugin tools, tool hooks and the current tool turn (``agent.tools``)."""
        if tools is not None:
            provide(HOST_TOOLS, PluginTools(tools))
        provide(HOST_TOOL_HOOKS, PluginToolHooks())
        provide(HOST_TOOL_TURN, current_tool_turn)

    def provide_channels(provide: CoreProvide) -> None:
        """Plugin channels, and the accounts and avatars they serve (``core.channels``)."""
        provide(HOST_CHANNELS, PluginChannels())
        if role_store is not None:
            provide(HOST_ACCOUNTS, PluginAccounts(role_store.accounts))
            provide(HOST_AVATARS, PluginAvatars(role_store.avatars))

    def provide_sessions(provide: CoreProvide) -> None:
        """The session manager and the session operations over it (``session``)."""
        if session_manager is None:
            return
        provide(HOST_SESSION_MANAGER, session_manager)
        if workspace is not None:
            presenter = DesktopSessionPresenter(None, relationship_runtime)
            sessions = HostPluginSessions(session_manager, workspace, presenter)
            provide(HOST_SESSIONS, sessions.as_capability())

    def provide_roles(provide: CoreProvide) -> None:
        """Roles, their models and the light model plugins use (``core.roles``)."""
        if role_store is not None:
            provide(HOST_ROLES, HostRoles(role_store).as_capability())
        if role_runtime_registry is not None:
            provide(HOST_ROLE_RUNTIME_REGISTRY, role_runtime_registry)
            provide(HOST_MODELS, HostRoleModels(role_runtime_registry).as_capability())
        if light_provider is not None:
            provide(HOST_LIGHT_PROVIDER, light_provider)
        if light_model is not None:
            provide(HOST_LIGHT_MODEL, light_model)

    def provide_scene(provide: CoreProvide) -> None:
        """Plugin demand for scene observations (``core.scene``)."""
        provide(HOST_SCENE_OBSERVATIONS, PluginSceneObservations(scene_observations))

    def provide_memory(provide: CoreProvide) -> None:
        """The memory plugin's setup surface (``bootstrap.memory_capabilities``)."""
        if workspace is not None and role_store is not None:
            provide(
                HOST_MEMORY,
                HostMemoryCapability(workspace, role_store, memory_engine),
            )

    def provide_processes(provide: CoreProvide) -> None:
        """Host-owned native processes and distributed resources."""
        provide(HOST_PROCESSES, HostProcesses().as_capability())
        # Typed as the plugin contract, so pyright checks the host implementation.
        resources: Resources = HostResources()
        provide(HOST_RESOURCES, resources)

    def provide_conversation(provide: CoreProvide) -> None:
        """External turns, background results and bot commands (``conversation``)."""
        if external_turns is not None:
            provide(HOST_EXTERNAL_TURNS, external_turns)
        if background_results is not None:
            provide(HOST_BACKGROUND_RESULTS, background_results)
        provide(HOST_BOT_COMMANDS, PluginBotCommands())

    def provide_background(provide: CoreProvide) -> None:
        """Plugin-scoped background tasks (``core.common``)."""
        provide(HOST_BACKGROUND, PluginBackground())

    def provide_proactive_gates(provide: CoreProvide) -> None:
        """Plugin proactive gates (``agent.core.proactive_turn``; P3 deletes them)."""
        provide(HOST_PROACTIVE_GATES, PluginProactiveGates())

    def provide_bridge(provide: CoreProvide) -> None:
        """The plugin RPC registry and the ``rpc`` capability over it (bridge)."""
        provide(HOST_BRIDGE, rpc)
        provide(HOST_RPC, PluginRpc(rpc, event_bus))

    def provide_events(provide: CoreProvide) -> None:
        """Plugin-scoped views of the event bus (``bus``)."""
        provide(HOST_EVENTS, PluginEvents(event_bus))

    return (
        provide_bridge,
        provide_events,
        provide_diagnostics,
        provide_config_references,
        provide_tools,
        provide_channels,
        provide_sessions,
        provide_roles,
        provide_scene,
        provide_memory,
        provide_processes,
        provide_conversation,
        provide_background,
        provide_proactive_gates,
    )
