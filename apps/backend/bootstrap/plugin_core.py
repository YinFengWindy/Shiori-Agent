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
    HOST_ACCOUNTS,
    HOST_AVATARS,
    HOST_BACKGROUND,
    HOST_BACKGROUND_RESULTS,
    HOST_BRIDGE,
    HOST_CHANNELS,
    HOST_CONFIG_REFERENCES,
    HOST_HTTP,
    HOST_EVENTS,
    HOST_EXTERNAL_TURNS,
    HOST_LIGHT_MODEL,
    HOST_LIGHT_PROVIDER,
    HOST_MEMORY,
    HOST_MODELS,
    HOST_PROCESS_RESOURCES,
    HOST_PROCESSES,
    HOST_RESOURCES,
    HOST_RPC,
    HOST_ROLES,
    HOST_SCENE_OBSERVATIONS,
    HOST_SESSIONS,
    HOST_TOOL_TURN,
    HOST_TOOLS,
    HOST_WORKSPACE,
    CoreModule,
    HOST_BUILT_KEYS,
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
from core.scene.demand import SceneObservationDemand
from core.scene.plugin_capability import PluginSceneObservations
from desktop_bridge.method_policy import MethodPolicy
from desktop_bridge.plugin_capability import PluginRpc
from desktop_bridge.session_presenter import DesktopSessionPresenter
from infra.process.plugin_capability import HostProcesses
from session.manager import SessionManager
from session.plugin_capability import HostSessions
from shiori_sdk.background_results import BackgroundResults
from shiori_sdk.commands import CommandRegistry
from shiori_sdk.core.conversation import COMMANDS
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
    SCENE_OBSERVATIONS,
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
    that bus. ``scene_observations`` is the demand registry the scene
    controller reads.

    The rest back capabilities; when one is None (host tests), a plugin
    declaring a capability over it fails before setup:

    - ``tools``: the generation's tool registry.
    - ``role_store``: the canonical role store, behind ``roles``, ``accounts``
      and ``avatars`` (its account index and avatar cache) and, with the
      ``workspace``, ``memory``.
    - ``session_manager``: the ``sessions`` socket (``SESSIONS``) and, with
      the ``workspace`` holding session media, session metadata
      (``host.sessions`` and ``SESSION_STORE``), whose payloads the desktop
      presenter projects with ``relationship_runtime``.
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
    scene_observations: SceneObservationDemand
    # The same directory as ``PluginGenerationSettings.workspace``: there the
    # kernel's trust store, execution identity and KV root; here the
    # ``workspace``, ``memory`` and ``sessions`` capabilities.
    workspace: Path | None
    tools: ToolRegistry | None
    role_store: RoleStore | None
    session_manager: SessionManager | None
    relationship_runtime: object
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

    A binder is stored as itself. ``PluginSetupContext.require`` calls
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
            tools = PluginTools(inputs.tools)
            provide(HOST_TOOLS, tools)
            _publish(provide, TOOLS, tools)
        provide(HOST_TOOL_TURN, current_tool_turn)
        provide(TOOL_TURN, current_tool_turn)

    def provide_channels(provide: CoreProvide) -> None:
        """Plugin channels, and the accounts and avatars they serve (``core.channels``)."""
        channels = PluginChannels()
        provide(HOST_CHANNELS, channels)
        _publish(provide, CHANNELS, channels)
        if inputs.role_store is not None:
            accounts = PluginAccounts(inputs.role_store.accounts)
            avatars = PluginAvatars(inputs.role_store.avatars)
            provide(HOST_ACCOUNTS, accounts)
            provide(HOST_AVATARS, avatars)
            _publish(provide, ACCOUNTS, accounts)
            _publish(provide, AVATARS, avatars)

    def provide_sessions(provide: CoreProvide) -> None:
        """The sessions socket and session media (``session``)."""
        if inputs.session_manager is None:
            return
        # Typed as the plugin contract, so pyright checks the host implementation.
        sessions_api: Sessions = inputs.session_manager
        provide(SESSIONS, sessions_api)
        if inputs.workspace is not None:
            presenter = DesktopSessionPresenter(None, inputs.relationship_runtime)
            # Typed as the plugin contract, so pyright checks the host implementation.
            sessions: PluginSessions = HostSessions(
                inputs.session_manager, inputs.workspace, presenter
            )
            provide(HOST_SESSIONS, sessions)
            provide(SESSION_STORE, sessions)

    def provide_roles(provide: CoreProvide) -> None:
        """Roles, their models, and the main and light chat pairs (``core.roles``)."""
        # Typed as the plugin contracts, so pyright checks the host implementations.
        if inputs.role_store is not None:
            roles: Roles = HostRoles(inputs.role_store)
            provide(HOST_ROLES, roles)
            provide(ROLES, roles)
        if inputs.role_runtime_registry is not None:
            models: RoleModels = HostRoleModels(inputs.role_runtime_registry)
            provide(HOST_MODELS, models)
            provide(MODELS, models)
        if inputs.provider is not None:
            provide(MAIN_PROVIDER, inputs.provider)
        if inputs.model is not None:
            provide(MAIN_MODEL, inputs.model)
        if inputs.light_provider is not None:
            provide(HOST_LIGHT_PROVIDER, inputs.light_provider)
            provide(LIGHT_PROVIDER, inputs.light_provider)
        if inputs.light_model is not None:
            provide(HOST_LIGHT_MODEL, inputs.light_model)
            provide(LIGHT_MODEL, inputs.light_model)

    def provide_scene(provide: CoreProvide) -> None:
        """Plugin demand for scene observations (``core.scene``)."""
        scene = PluginSceneObservations(inputs.scene_observations)
        provide(HOST_SCENE_OBSERVATIONS, scene)
        _publish(provide, SCENE_OBSERVATIONS, scene)

    def provide_memory(provide: CoreProvide) -> None:
        """The memory plugin's surface (``bootstrap.memory_capabilities``).

        The engine itself is provided by a plugin as ``MEMORY_ENGINE``.
        """
        if inputs.workspace is not None and inputs.role_store is not None:
            memory = HostMemoryCapability(inputs.workspace, inputs.role_store)
            provide(HOST_MEMORY, memory)
            provide(MEMORY, memory)

    def provide_processes(provide: CoreProvide) -> None:
        """Native processes, process-owned resources and distributed resources."""
        # Typed as the plugin contracts, so pyright checks the host implementations.
        processes: Processes = HostProcesses()
        provide(HOST_PROCESSES, processes)
        provide(PROCESSES, processes)
        if inputs.process_resources is not None:
            attachments = PluginProcessResourceAttachments(inputs.process_resources)
            provide(HOST_PROCESS_RESOURCES, attachments)
            _publish(provide, PROCESS_RESOURCES, attachments)
        resources: Resources = HostResources()
        provide(HOST_RESOURCES, resources)
        provide(RESOURCES, resources)

    def provide_conversation(provide: CoreProvide) -> None:
        """External turns, background results and ``COMMANDS`` (``conversation``)."""
        if inputs.external_turns is not None:
            provide(HOST_EXTERNAL_TURNS, inputs.external_turns)
            provide(EXTERNAL_TURNS, inputs.external_turns)
        if inputs.background_results is not None:
            provide(HOST_BACKGROUND_RESULTS, inputs.background_results)
            provide(BACKGROUND_RESULTS, inputs.background_results)
        provide(COMMANDS, CommandRegistry())

    def provide_background(provide: CoreProvide) -> None:
        """Plugin-scoped background tasks (``core.common``)."""
        background = PluginBackground()
        provide(HOST_BACKGROUND, background)
        _publish(provide, BACKGROUND, background)

    def provide_bridge(provide: CoreProvide) -> None:
        """The plugin RPC registry and the ``rpc`` capability over it (bridge)."""
        provide(HOST_BRIDGE, inputs.rpc)
        rpc = PluginRpc(inputs.rpc, inputs.event_bus)
        provide(HOST_RPC, rpc)
        _publish(provide, RPC, rpc)

    def provide_events(provide: CoreProvide) -> None:
        """Plugin-scoped views of the event bus (``bus``)."""
        events = PluginEvents(inputs.event_bus)
        provide(HOST_EVENTS, events)
        _publish(provide, EVENTS, events)

    def provide_host_passthrough(provide: CoreProvide) -> None:
        """The workspace directory and the shared external HTTP requester."""
        if inputs.workspace is not None:
            provide(HOST_WORKSPACE, inputs.workspace)
            provide(WORKSPACE, inputs.workspace)
        if inputs.http is not None:
            provide(HOST_HTTP, inputs.http)
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
        provide_memory,
        provide_processes,
        provide_conversation,
        provide_background,
        provide_host_passthrough,
    )
