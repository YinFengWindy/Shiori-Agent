"""按产品扩展点划分的 capability 实现：插件只拿到 manifest 声明的窄接口。"""

from __future__ import annotations

import asyncio
import inspect
import logging
from typing import TYPE_CHECKING, Any
from uuid import uuid4

from agent.plugin_host.diagnostics import ChannelDeclarationError
from agent.plugin_host.effects import EffectScope
from agent.plugin_host.tool_hooks import PluginToolHook, build_hook_name

if TYPE_CHECKING:
    from agent.core.proactive_turn.gates import ProactiveGate
    from agent.plugin_host.rpc import PluginRpcRegistry, RpcHandler
    from agent.tool_hooks.base import ToolHook
    from desktop_bridge.method_policy import Concurrency
    from infra.channels.contract import Channel
    from core.accounts import AccountRegistry, AccountSnapshot, ConnectionState

logger = logging.getLogger(__name__)

# Shiori 定义的 7 个 phase 槽位；顺序与 AgentLoop 接线一致
PHASE_SLOTS = (
    "before_turn",
    "before_reasoning",
    "prompt_render",
    "before_step",
    "after_step",
    "after_reasoning",
    "after_turn",
)


class PluginContributions:
    """单个插件贡献的运行时对象集合；随插件卸载整体废弃。"""

    def __init__(self) -> None:
        self.phase_modules: dict[str, list[object]] = {slot: [] for slot in PHASE_SLOTS}
        self.tool_hooks: list[ToolHook] = []
        self.proactive_gates: list[ProactiveGate] = []
        self.channels: list[Channel] = []
        self.tool_names: list[str] = []
        self.bot_commands: list[tuple[str, str]] = []


def contribute_to_list[T](
    target: list[T],
    item: T,
    *,
    effects: EffectScope,
    label: str,
) -> None:
    """把一项贡献登记进目标列表，并登记"从列表移除"的可回滚 effect。

    四类列表型 capability（tool hook / proactive gate / channel / bot command）
    共用此实现，保证登记与撤销形状一致；移除守卫使重复处置保持幂等。
    """
    effects.ensure_active(label)
    target.append(item)

    def discard() -> None:
        if item in target:
            target.remove(item)

    effects.add(label, discard)


class ToolsCapability:
    """注册插件工具到 ToolRegistry；卸载时通过 effect 反注册。"""

    def __init__(
        self,
        registry: Any,
        effects: EffectScope,
        contributions: PluginContributions,
        plugin_id: str,
    ) -> None:
        self._registry = registry
        self._effects = effects
        self._contributions = contributions
        self._plugin_id = plugin_id

    def register(
        self,
        tool: Any,
        *,
        risk: str = "read-write",
        always_on: bool = False,
        search_hint: str | None = None,
    ) -> None:
        if self._registry is None:
            raise RuntimeError(
                f"插件 {self._plugin_id} 请求 tools 能力，但宿主未提供 ToolRegistry"
            )
        name = str(tool.name)
        self._effects.ensure_active(f"tool:{name}")
        self._registry.register(
            tool,
            risk=risk,
            always_on=always_on,
            search_hint=search_hint,
            source_type="plugin",
            source_name=self._plugin_id,
        )
        # 工具除了从贡献清单移除，还要反注册出 ToolRegistry，故不复用列表 helper
        self._contributions.tool_names.append(name)
        self._effects.add(f"tool:{name}", lambda: self._unregister(name))

    def _unregister(self, name: str) -> None:
        if self._registry is not None:
            self._registry.unregister(name)
        if name in self._contributions.tool_names:
            self._contributions.tool_names.remove(name)

    def get_tool(self, name: str) -> Any:
        """Looks up another tool by name (e.g. to invoke it directly).

        Read-only passthrough to the underlying ``ToolRegistry`` — unlike
        ``register``, there is no lifecycle to own here, so this does not need
        an ``EffectScope`` entry. Registration itself must still go through
        ``register`` above so the tool is reclaimed on unload; this only lets
        a plugin look up and call a tool (its own or another's).
        """
        if self._registry is None:
            return None
        return self._registry.get_tool(name)

    def get_context(self) -> dict[str, str]:
        """Returns the current tool-call context (read-only passthrough)."""
        if self._registry is None:
            return {}
        return self._registry.get_context()


class LifecycleCapability:
    """向 Shiori 定义的 phase 槽位贡献模块；槽位顺序语义仍由核心拥有。"""

    def __init__(
        self, contributions: PluginContributions, effects: EffectScope
    ) -> None:
        self._contributions = contributions
        self._effects = effects

    def contribute(self, slot: str, modules: list[object]) -> None:
        if slot not in PHASE_SLOTS:
            raise ValueError(f"未知 phase 槽位: {slot}")
        self._effects.ensure_active(f"phase:{slot}")
        target = self._contributions.phase_modules[slot]
        target.extend(modules)

        def remove_contributed() -> None:
            for module in modules:
                if module in target:
                    target.remove(module)

        self._effects.add(f"phase:{slot}:{len(modules)}", remove_contributed)


class ToolHooksCapability:
    """贡献工具执行前置 hook（ToolExecutor pre_hook 链）。"""

    def __init__(
        self,
        contributions: PluginContributions,
        effects: EffectScope,
        plugin_id: str,
    ) -> None:
        self._contributions = contributions
        self._effects = effects
        self._plugin_id = plugin_id

    def add(self, hook: "ToolHook") -> None:
        contribute_to_list(
            self._contributions.tool_hooks,
            hook,
            effects=self._effects,
            label=f"tool_hook:{getattr(hook, 'name', hook)}",
        )

    def add_handler(
        self,
        handler: Any,
        *,
        tool_name_filter: str | None = None,
        handler_name: str | None = None,
    ) -> None:
        """把函数式 pre-tool handler 包装为 PluginToolHook 并登记。

        hook 名统一在这里生成（``build_hook_name``），插件不再需要各自导入宿主的
        ``PluginToolHook``、手写 f-string 拼接或维护 ``_PLUGIN_NAME`` 常量（#182 评审）。
        包装函数或 partial 可以显式提供 ``handler_name``，保持公开诊断名称稳定。
        """
        resolved_name = handler_name or getattr(handler, "__name__", repr(handler))
        hook = PluginToolHook(
            name=build_hook_name(self._plugin_id, resolved_name),
            handler=handler,
            tool_name_filter=tool_name_filter,
        )
        self.add(hook)
        logger.info("插件 tool hook 已注册: %s", hook.name)


class ProactiveGatesCapability:
    """贡献参与主动 tick 准入的 gate；不允许直接投递消息。"""

    def __init__(
        self, contributions: PluginContributions, effects: EffectScope
    ) -> None:
        self._contributions = contributions
        self._effects = effects

    def add(self, gate: "ProactiveGate") -> None:
        contribute_to_list(
            self._contributions.proactive_gates,
            gate,
            effects=self._effects,
            label=f"proactive_gate:{getattr(gate, 'name', gate)}",
        )


class ChannelsCapability:
    """贡献渠道 adapter；渠道宿主接管其生命周期。

    只接受 manifest ``channels`` 静态声明过的渠道名：绑定面板依据声明列出渠道，
    未声明的名字会让已落盘的绑定与实际贡献对不上。
    """

    def __init__(
        self,
        contributions: PluginContributions,
        effects: EffectScope,
        *,
        plugin_id: str,
        declared: frozenset[str],
    ) -> None:
        self._contributions = contributions
        self._effects = effects
        self._plugin_id = plugin_id
        self._declared = declared

    def add(self, channel: "Channel") -> None:
        name = getattr(channel, "name", None)
        if name not in self._declared:
            raise ChannelDeclarationError(self._plugin_id, str(name), self._declared)
        contribute_to_list(
            self._contributions.channels,
            channel,
            effects=self._effects,
            label=f"channel:{getattr(channel, 'name', channel)}",
        )


class AccountsCapability:
    """Plugin-scoped registration and reporting for communication accounts."""

    def __init__(
        self,
        registry: "AccountRegistry",
        effects: EffectScope,
        plugin_id: str,
        generation: str,
    ) -> None:
        self._registry = registry
        self._effects = effects
        self._plugin_id = plugin_id
        self._generation = generation
        self._token = uuid4().hex
        self._registered: set[str] = set()

    def register(
        self,
        *,
        platform: str,
        platform_account_id: str,
        config_ref: str,
        display_name: str = "",
        avatar_url: str = "",
    ) -> "AccountSnapshot":
        """Registers an identity verified by the plugin; no credentials are accepted."""
        self._effects.ensure_active("account:register")
        snapshot = self._registry.register(
            plugin_id=self._plugin_id,
            platform=platform,
            platform_account_id=platform_account_id,
            config_ref=config_ref,
            token=self._token,
            generation=self._generation,
            display_name=display_name,
            avatar_url=avatar_url,
        )
        account_id = snapshot.record.id
        if account_id not in self._registered:
            self._registered.add(account_id)
            self._effects.add(
                f"account:{account_id}",
                lambda: self._registry.release(
                    account_id, self._token, generation=self._generation
                ),
            )
        return snapshot

    def report(
        self,
        account_id: str,
        *,
        connection: "ConnectionState",
        capabilities: frozenset[str] = frozenset(),
        error: str = "",
    ) -> "AccountSnapshot":
        """Reports connection, authentication, capability, or failure changes."""
        self._effects.ensure_active(f"account:{account_id}:report")
        if account_id not in self._registered:
            raise PermissionError("Account was not registered by this plugin instance")
        return self._registry.report(
            account_id,
            self._token,
            generation=self._generation,
            connection=connection,
            capabilities=capabilities,
            error=error,
        )

    def unregister(self, account_id: str) -> None:
        """Stops one account while retaining its saved identity and assignment."""
        self._effects.ensure_active(f"account:{account_id}:unregister")
        if account_id not in self._registered:
            raise PermissionError("Account was not registered by this plugin instance")
        self._registry.unregister(account_id, self._token, generation=self._generation)


class BotCommandsCapability:
    """贡献 bot 命令（如 Telegram `/xxx`）；卸载时随 effect 从聚合列表摘除。"""

    def __init__(
        self, contributions: PluginContributions, effects: EffectScope
    ) -> None:
        self._contributions = contributions
        self._effects = effects

    def add(self, command: str, description: str) -> None:
        contribute_to_list(
            self._contributions.bot_commands,
            (command, description),
            effects=self._effects,
            label=f"bot_command:{command}",
        )


class RpcCapability:
    """ctx.rpc：向 ``plugin.<id>.<method>`` 命名空间登记桥接可调用方法。

    并发/准入语义复用桌面桥接的 ``MethodPolicy``；未声明时回落到保守默认
    （非只读并发、非豁免准入），由插件按需通过参数放宽。卸载/回滚时经
    EffectScope 反注册，使方法可调用性与插件在架状态严格同步。
    """

    def __init__(
        self,
        registry: "PluginRpcRegistry",
        effects: EffectScope,
        plugin_id: str,
        event_bus: Any = None,
    ) -> None:
        self._registry = registry
        self._effects = effects
        self._plugin_id = plugin_id
        self._event_bus = event_bus

    async def emit(self, name: str, payload: dict[str, Any]) -> bool:
        """Reports transport delivery, not individual renderer consumption."""
        from agent.plugin_host.bridge_events import PluginBridgeEvent

        from agent.plugin_host.communication import communication_name

        self._effects.ensure_active(f"event:{name}")
        communication_name(name)
        if self._event_bus is None:
            raise RuntimeError("插件事件传输不可用")
        event = PluginBridgeEvent(
            f"plugin.{self._plugin_id}.{name}", payload, self._registry
        )
        await self._event_bus.emit(event)
        return event.dispatched

    def register(
        self,
        name: str,
        handler: "RpcHandler",
        *,
        concurrency: "Concurrency | None" = None,
        admission_exempt: bool = False,
    ) -> None:
        # 局部导入：核心插件运行时不在模块加载期就拉入桌面桥接的完整依赖链，
        # 只在插件真正调用 ctx.rpc.register 时（应用已启动）才需要这些类型。
        from desktop_bridge.method_policy import Concurrency, Handler, MethodPolicy

        full_name = f"plugin.{self._plugin_id}.{name}"
        self._effects.ensure_active(f"rpc:{full_name}")
        policy = MethodPolicy(
            concurrency=concurrency or Concurrency.MUTATION,
            admission_exempt=admission_exempt,
            handler=Handler.GENERATION,
        )
        self._registry.register(full_name, self._plugin_id, handler, policy)
        self._effects.add(
            f"rpc:{full_name}", lambda: self._registry.unregister(full_name)
        )


class BackgroundCapability:
    """启动可取消后台任务；插件卸载时任务被取消并等待退出。"""

    def __init__(self, effects: EffectScope, plugin_id: str) -> None:
        self._effects = effects
        self._plugin_id = plugin_id

    def spawn(self, coro: Any, *, name: str) -> asyncio.Task[Any]:
        """启动作用域任务；开始卸载后拒绝启动并关闭尚未运行的协程。"""
        try:
            self._effects.ensure_active(f"background:{name}")
        except RuntimeError:
            if inspect.iscoroutine(coro):
                coro.close()
            raise
        task: asyncio.Task[Any] = asyncio.create_task(
            coro, name=f"plugin:{self._plugin_id}:{name}"
        )
        self._effects.add(f"background:{name}", lambda: self._cancel(task))
        return task

    @staticmethod
    async def _cancel(task: asyncio.Task[Any]) -> None:
        if task.done():
            return
        _ = task.cancel()
        try:
            await task
        except (
            asyncio.CancelledError,
            Exception,
        ):  # noqa: BLE001 - 卸载路径只收敛不传播
            pass
