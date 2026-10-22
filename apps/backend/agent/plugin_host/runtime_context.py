"""插件作用域运行时上下文：只暴露 manifest 声明的 capability，取代旧上帝对象。"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import Any

from agent.plugin_host.capabilities import LifecycleCapability, RpcCapability
from shiori_sdk.kernel import Scope
from agent.plugin_host.host_service_requirements import provided_service
from shiori_sdk.services import PluginServices, ServiceProviderContext
from shiori_sdk.runtime import Dispose
from agent.plugin_host.manifest import PluginManifest
from shiori_sdk import PluginRuntimeContext as SdkRuntimeContext
from shiori_sdk.memory.context import MemoryCapability, MemoryPluginContext
from shiori_sdk.extensions import (
    HookPluginContext,
    CommandPluginContext,
    ObservePluginContext,
    ConfigValues,
    BotCommands,
    Dependencies,
    BackgroundTasks,
    PrivateStorage,
)
from shiori_sdk.tool_hooks import ToolHooksCapability
from shiori_sdk.memory.engine import MemoryEngine
from shiori_sdk.diagnostics import Diagnostics
from shiori_sdk.runtime import (
    CapabilityNotGranted,
)
from shiori_sdk.runtime import (
    EventsCapability,
)


from shiori_sdk.plugin_services import ServicePluginContext, RuntimeLifecycle
from shiori_sdk.roles import Roles, SceneObservations
from shiori_sdk.models import ChatProvider, RoleModels
from shiori_sdk.sessions import PluginSessions, SessionUndo
from shiori_sdk.external_turns import ExternalTurns
from shiori_sdk.background_results import BackgroundResults
from shiori_sdk.process_resources import PluginProcessResources
from shiori_sdk.tools import ToolsCapability as SdkToolsCapability
from agent.plugin_host.kv import PluginKVStore
from shiori_sdk.http import HttpClient
from shiori_sdk.processes import Processes, Resources, ToolTurn
from shiori_sdk.channels.context import ChannelPluginContext, ChannelsCapability
from shiori_sdk.accounts.capability import AccountsCapability
from shiori_sdk.channels.avatars import AvatarsCapability


class PluginSetupContext:
    """v2 插件在 setup(ctx) 中拿到的唯一句柄。

    通过属性访问已授予的 capability（ctx.tools / ctx.events / ctx.kv / ...）；
    未声明的能力访问时抛 CapabilityNotGranted；已声明但宿主缺少支撑服务时抛
    HostServiceUnavailable（内核在 setup 前已校验，这里是同一规则的属性侧）。
    """

    def __init__(
        self,
        *,
        plugin_id: str,
        plugin_dir: Path,
        manifest: PluginManifest,
        effects: Scope,
        capabilities: dict[str, Any],
        publish_api: Callable[[object], None] | None = None,
        lifecycle: LifecycleCapability | None = None,
        events: EventsCapability | None = None,
        memory: MemoryCapability | None = None,
        rpc: RpcCapability | None = None,
        workspace: Path | None = None,
        config: ConfigValues | None = None,
        tool_hooks: ToolHooksCapability | None = None,
        bot_commands: BotCommands | None = None,
        dependencies: Dependencies | None = None,
        background: BackgroundTasks | None = None,
        storage: PrivateStorage | None = None,
        diagnostics: Diagnostics | None = None,
        session_manager: SessionUndo | None = None,
        memory_engine: MemoryEngine | None = None,
        roles: Roles | None = None,
        models: RoleModels | None = None,
        sessions: PluginSessions | None = None,
        external_turns: ExternalTurns | None = None,
        background_results: BackgroundResults | None = None,
        process_resources: PluginProcessResources | None = None,
        tools: SdkToolsCapability | None = None,
        kv: PluginKVStore | None = None,
        http: HttpClient | None = None,
        resources: Resources | None = None,
        processes: Processes | None = None,
        tool_turn: Callable[[], ToolTurn] | None = None,
        runtime: RuntimeLifecycle | None = None,
        scene_observations: SceneObservations | None = None,
        light_provider: ChatProvider | None = None,
        light_model: str | None = None,
        role_runtime_registry: object = None,
        proactive_gates: Any = None,
        channels: ChannelsCapability | None = None,
        accounts: AccountsCapability | None = None,
        avatars: AvatarsCapability | None = None,
        services: PluginServices | None = None,
    ) -> None:
        self.plugin_id = plugin_id
        self.plugin_dir = plugin_dir
        self.manifest = manifest
        self._effects = effects
        self._capabilities = capabilities
        self._publish_api = publish_api
        self._lifecycle = lifecycle
        self._events = events
        self._memory = memory
        self._rpc = rpc
        self._workspace = workspace
        self._config = config
        self._tool_hooks = tool_hooks
        self._bot_commands = bot_commands
        self._dependencies = dependencies
        self._background = background
        self._storage = storage
        self._diagnostics = diagnostics
        self._session_manager = session_manager
        self._memory_engine = memory_engine
        self._roles = roles
        self._models = models
        self._sessions = sessions
        self._external_turns = external_turns
        self._background_results = background_results
        self._process_resources = process_resources
        self._tools = tools
        self._kv = kv
        self._http = http
        self._resources = resources
        self._processes = processes
        self._tool_turn = tool_turn
        self._runtime = runtime
        self._scene_observations = scene_observations
        self._light_provider = light_provider
        self._light_model = light_model
        self._role_runtime_registry = role_runtime_registry
        self._proactive_gates = proactive_gates
        self._channels = channels
        self._accounts = accounts
        self._avatars = avatars
        self._services = services

    @property
    def services(self) -> PluginServices:
        """Return this plugin's explicitly granted public service registration."""
        if "services" not in self.granted or self._services is None:
            raise CapabilityNotGranted("Plugin did not request services")
        return self._services

    def as_service_provider_context(self) -> ServiceProviderContext:
        """Check the public service setup surface without dynamic attributes."""
        return self

    def as_sdk_context(self) -> SdkRuntimeContext:
        """Checks the setup boundary against this static base, without __getattr__."""
        return self

    def as_memory_context(self) -> MemoryPluginContext:
        """Checks the memory setup surface without relying on __getattr__."""
        return self

    def expose(self, api: object) -> None:
        """Publishes this plugin's API for declared dependents in the same generation."""
        if self._publish_api is None:
            raise RuntimeError("插件导出接口不可用")
        self._publish_api(api)

    @property
    def granted(self) -> tuple[str, ...]:
        """Returns granted capability names, for diagnostics."""
        return tuple(sorted(self._capabilities))

    def _core_capability[T](self, capability: str, value: T | None) -> T:
        """A capability filled from ``core_keys.CORE_CAPABILITIES``.

        ``bind_core_capabilities`` fails setup when a declared one has no core
        provider, so ``value`` is None only when the plugin did not declare it.
        """
        if capability not in self.granted or value is None:
            raise CapabilityNotGranted(f"Plugin did not request {capability}")
        return value

    def _provided[T](self, capability: str, value: T | None) -> T:
        """Separates an undeclared capability from a host that lacks its service."""
        if capability not in self.granted:
            raise CapabilityNotGranted(f"Plugin did not request {capability}")
        return provided_service(self.plugin_id, capability, value)

    def effect(self, label: str, dispose: Dispose) -> None:
        """登记资源清理；卸载先停用/退订 ctx.events.on，再逆序撤销其它 effect。

        disposer 可同步或异步；单项失败仍继续清理。事件订阅与 effect 的登记
        先后不影响退订优先规则；开始清理后拒绝新登记。
        """
        _ = self._effects.effect(dispose, f"custom:{label}")

    @property
    def lifecycle(self) -> LifecycleCapability:
        """Returns the explicitly typed lifecycle capability granted by the kernel."""
        if self._lifecycle is None:
            raise CapabilityNotGranted(
                f"插件 {self.plugin_id} 未声明 capability 'lifecycle'"
            )
        return self._lifecycle

    @property
    def events(self) -> EventsCapability:
        """Returns the explicitly typed scoped event bus granted by the kernel."""
        if self._events is None:
            raise CapabilityNotGranted(
                f"插件 {self.plugin_id} 未声明 capability 'events'"
            )
        return self._events

    @property
    def memory(self) -> MemoryCapability:
        """Returns the typed memory surface granted to this plugin."""
        return self._core_capability("memory", self._memory)

    @property
    def rpc(self) -> RpcCapability:
        """Returns scoped RPC registration without a dynamic capability escape."""
        if self._rpc is None:
            raise CapabilityNotGranted("Plugin did not request rpc capability")
        return self._rpc

    @property
    def workspace(self) -> Path:
        """Return the explicitly granted workspace capability."""
        return self._provided("workspace", self._workspace)

    @property
    def config(self) -> ConfigValues:
        """Return the explicitly granted config capability."""
        if "config" not in self.granted or self._config is None:
            raise CapabilityNotGranted("Plugin did not request config")
        return self._config

    @property
    def tool_hooks(self) -> ToolHooksCapability:
        """Return the explicitly granted tool_hooks capability."""
        return self._core_capability("tool_hooks", self._tool_hooks)

    @property
    def bot_commands(self) -> BotCommands:
        """Return the explicitly granted bot_commands capability."""
        return self._core_capability("bot_commands", self._bot_commands)

    @property
    def dependencies(self) -> Dependencies:
        """Return the explicitly granted dependencies capability."""
        if "dependencies" not in self.granted or self._dependencies is None:
            raise CapabilityNotGranted("Plugin did not request dependencies")
        return self._dependencies

    @property
    def background(self) -> BackgroundTasks:
        """Return the explicitly granted background capability."""
        return self._core_capability("background", self._background)

    @property
    def storage(self) -> PrivateStorage:
        """Return the explicitly granted storage capability."""
        if "storage" not in self.granted or self._storage is None:
            raise CapabilityNotGranted("Plugin did not request storage")
        return self._storage

    @property
    def diagnostics(self) -> Diagnostics:
        """Return the explicitly granted diagnostics capability."""
        return self._core_capability("diagnostics", self._diagnostics)

    @property
    def session_manager(self) -> SessionUndo:
        """Return the explicitly granted session_manager capability."""
        return self._core_capability("session_manager", self._session_manager)

    @property
    def memory_engine(self) -> MemoryEngine | None:
        """Return the explicitly granted memory_engine capability.

        ``None`` is a valid host state (memory disabled in config), not a missing
        service, so it is returned rather than raised.
        """
        if "memory_engine" not in self.granted:
            raise CapabilityNotGranted("Plugin did not request memory_engine")
        return self._memory_engine

    def as_hook_context(self) -> HookPluginContext:
        """Check the hook setup boundary without dynamic attributes."""
        return self

    def as_command_context(self) -> CommandPluginContext:
        """Check the command setup boundary without dynamic attributes."""
        return self

    def as_observe_context(self) -> ObservePluginContext:
        """Check the observe setup boundary without dynamic attributes."""
        return self

    @property
    def roles(self) -> Roles:
        """Return the explicitly granted roles SDK capability."""
        return self._core_capability("roles", self._roles)

    @property
    def models(self) -> RoleModels:
        """Return the explicitly granted models SDK capability."""
        return self._core_capability("models", self._models)

    @property
    def sessions(self) -> PluginSessions:
        """Return the explicitly granted sessions SDK capability."""
        return self._core_capability("sessions", self._sessions)

    @property
    def process_resources(self) -> PluginProcessResources:
        """Access process-owned resources through this generation attachment."""
        return self._provided("process_resources", self._process_resources)

    @property
    def background_results(self) -> BackgroundResults:
        """Capture role-bound background result destinations."""
        return self._core_capability("background_results", self._background_results)

    @property
    def external_turns(self) -> ExternalTurns:
        """Return the explicitly granted external-turn submission capability."""
        return self._core_capability("external_turns", self._external_turns)

    @property
    def tools(self) -> SdkToolsCapability:
        """Return the explicitly granted tools SDK capability."""
        return self._core_capability("tools", self._tools)

    @property
    def kv(self) -> PluginKVStore:
        """Return the explicitly granted kv SDK capability."""
        return self._provided("kv", self._kv)

    @property
    def http(self) -> HttpClient:
        """Return the explicitly granted http SDK capability."""
        return self._provided("http", self._http)

    @property
    def resources(self) -> Resources:
        """Return the explicitly granted resources SDK capability."""
        return self._core_capability("resources", self._resources)

    @property
    def processes(self) -> Processes:
        """Return the explicitly granted processes SDK capability."""
        return self._core_capability("processes", self._processes)

    @property
    def tool_turn(self) -> Callable[[], ToolTurn]:
        """Return the explicitly granted tool_turn SDK capability."""
        return self._core_capability("tool_turn", self._tool_turn)

    @property
    def runtime(self) -> RuntimeLifecycle:
        """Return the explicitly granted runtime SDK capability."""
        if "runtime" not in self.granted or self._runtime is None:
            raise CapabilityNotGranted("Plugin did not request runtime")
        return self._runtime

    @property
    def scene_observations(self) -> SceneObservations:
        """Return the explicitly granted scene_observations SDK capability."""
        return self._core_capability("scene_observations", self._scene_observations)

    @property
    def light_provider(self) -> ChatProvider:
        """Return the explicitly granted light_provider SDK capability."""
        return self._core_capability("light_provider", self._light_provider)

    @property
    def light_model(self) -> str:
        """Return the explicitly granted light_model SDK capability."""
        return self._core_capability("light_model", self._light_model)

    @property
    def proactive_gates(self) -> Any:
        """Return the explicitly granted proactive gate contributions (P3 deletes it)."""
        return self._core_capability("proactive_gates", self._proactive_gates)

    @property
    def role_runtime_registry(self) -> object:
        """Return the explicitly granted role runtime registry, passed through."""
        return self._core_capability(
            "role_runtime_registry", self._role_runtime_registry
        )

    def as_service_context(self) -> ServicePluginContext:
        """Check service injection without the legacy dynamic attribute path."""
        return self

    @property
    def channels(self) -> ChannelsCapability:
        """Return statically checked channel contribution services."""
        return self._core_capability("channels", self._channels)

    @property
    def accounts(self) -> AccountsCapability:
        """Return statically checked account registration and lifecycle services."""
        return self._core_capability("accounts", self._accounts)

    def as_channel_context(self) -> ChannelPluginContext:
        """Check the actual setup boundary without dynamic legacy attributes."""
        return self

    @property
    def avatars(self) -> AvatarsCapability:
        """Return the explicitly granted shared avatar-cache contract."""
        return self._core_capability("avatars", self._avatars)


class PluginRuntimeContext(PluginSetupContext):
    """Legacy capabilities for plugins awaiting migration; absent from SDK typing."""

    def __getattr__(self, name: str) -> Any:
        try:
            capabilities = object.__getattribute__(self, "_capabilities")
        except AttributeError as e:  # 构造未完成时保持原始 AttributeError 语义
            raise AttributeError(name) from e
        if name in capabilities:
            return capabilities[name]
        raise CapabilityNotGranted(
            f"插件 {self.plugin_id} 未声明 capability {name!r}；"
            f"已授予: {', '.join(self.granted) or '无'}"
        )
