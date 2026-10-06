"""插件作用域运行时上下文：只暴露 manifest 声明的 capability，取代旧上帝对象。"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import Any
from session.manager import SessionManager

from agent.plugin_host.capabilities import LifecycleCapability, RpcCapability
from agent.plugin_host.effects import EffectScope
from agent.plugin_host.host_service_requirements import provided_service
from shiori_sdk.voice import VoiceCapability, VoicePluginContext
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
from shiori_sdk.sessions import PluginSessions
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
        effects: EffectScope,
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
        session_manager: SessionManager | None = None,
        memory_engine: MemoryEngine | None = None,
        roles: Roles | None = None,
        models: RoleModels | None = None,
        sessions: PluginSessions | None = None,
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
        channels: ChannelsCapability | None = None,
        accounts: AccountsCapability | None = None,
        avatars: AvatarsCapability | None = None,
        voice: VoiceCapability | None = None,
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
        self._channels = channels
        self._accounts = accounts
        self._avatars = avatars
        self._voice = voice

    @property
    def voice(self) -> VoiceCapability:
        """Return this plugin's explicitly granted scoped voice slots."""
        if "voice" not in self.granted or self._voice is None:
            raise CapabilityNotGranted("Plugin did not request voice")
        return self._voice

    def as_voice_context(self) -> VoicePluginContext:
        """Check the public voice setup surface without dynamic attributes."""
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
        self._effects.add(f"custom:{label}", dispose)

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
        return self._provided("memory", self._memory)

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
        if "tool_hooks" not in self.granted or self._tool_hooks is None:
            raise CapabilityNotGranted("Plugin did not request tool_hooks")
        return self._tool_hooks

    @property
    def bot_commands(self) -> BotCommands:
        """Return the explicitly granted bot_commands capability."""
        if "bot_commands" not in self.granted or self._bot_commands is None:
            raise CapabilityNotGranted("Plugin did not request bot_commands")
        return self._bot_commands

    @property
    def dependencies(self) -> Dependencies:
        """Return the explicitly granted dependencies capability."""
        if "dependencies" not in self.granted or self._dependencies is None:
            raise CapabilityNotGranted("Plugin did not request dependencies")
        return self._dependencies

    @property
    def background(self) -> BackgroundTasks:
        """Return the explicitly granted background capability."""
        if "background" not in self.granted or self._background is None:
            raise CapabilityNotGranted("Plugin did not request background")
        return self._background

    @property
    def storage(self) -> PrivateStorage:
        """Return the explicitly granted storage capability."""
        if "storage" not in self.granted or self._storage is None:
            raise CapabilityNotGranted("Plugin did not request storage")
        return self._storage

    @property
    def diagnostics(self) -> Diagnostics:
        """Return the explicitly granted diagnostics capability."""
        if "diagnostics" not in self.granted or self._diagnostics is None:
            raise CapabilityNotGranted("Plugin did not request diagnostics")
        return self._diagnostics

    @property
    def session_manager(self) -> SessionManager:
        """Return the explicitly granted session_manager capability."""
        return self._provided("session_manager", self._session_manager)

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
        return self._provided("roles", self._roles)

    @property
    def models(self) -> RoleModels:
        """Return the explicitly granted models SDK capability."""
        return self._provided("models", self._models)

    @property
    def sessions(self) -> PluginSessions:
        """Return the explicitly granted sessions SDK capability."""
        return self._provided("sessions", self._sessions)

    @property
    def tools(self) -> SdkToolsCapability:
        """Return the explicitly granted tools SDK capability."""
        return self._provided("tools", self._tools)

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
        if "resources" not in self.granted or self._resources is None:
            raise CapabilityNotGranted("Plugin did not request resources")
        return self._resources

    @property
    def processes(self) -> Processes:
        """Return the explicitly granted processes SDK capability."""
        if "processes" not in self.granted or self._processes is None:
            raise CapabilityNotGranted("Plugin did not request processes")
        return self._processes

    @property
    def tool_turn(self) -> Callable[[], ToolTurn]:
        """Return the explicitly granted tool_turn SDK capability."""
        if "tool_turn" not in self.granted or self._tool_turn is None:
            raise CapabilityNotGranted("Plugin did not request tool_turn")
        return self._tool_turn

    @property
    def runtime(self) -> RuntimeLifecycle:
        """Return the explicitly granted runtime SDK capability."""
        if "runtime" not in self.granted or self._runtime is None:
            raise CapabilityNotGranted("Plugin did not request runtime")
        return self._runtime

    @property
    def scene_observations(self) -> SceneObservations:
        """Return the explicitly granted scene_observations SDK capability."""
        return self._provided("scene_observations", self._scene_observations)

    @property
    def light_provider(self) -> ChatProvider:
        """Return the explicitly granted light_provider SDK capability."""
        return self._provided("light_provider", self._light_provider)

    @property
    def light_model(self) -> str:
        """Return the explicitly granted light_model SDK capability."""
        return self._provided("light_model", self._light_model)

    def as_service_context(self) -> ServicePluginContext:
        """Check service injection without the legacy dynamic attribute path."""
        return self

    @property
    def channels(self) -> ChannelsCapability:
        """Return statically checked channel contribution services."""
        if "channels" not in self.granted or self._channels is None:
            raise CapabilityNotGranted("Plugin did not request channels")
        return self._channels

    @property
    def accounts(self) -> AccountsCapability:
        """Return statically checked account registration and lifecycle services."""
        return self._provided("accounts", self._accounts)

    def as_channel_context(self) -> ChannelPluginContext:
        """Check the actual setup boundary without dynamic legacy attributes."""
        return self

    @property
    def avatars(self) -> AvatarsCapability:
        """Return the explicitly granted shared avatar-cache contract."""
        return self._provided("avatars", self._avatars)


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
