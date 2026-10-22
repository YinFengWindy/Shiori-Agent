"""按产品扩展点划分的 capability 实现：插件只拿到 manifest 声明的窄接口。"""

from __future__ import annotations

from collections.abc import Iterable, Sequence

from typing import TYPE_CHECKING, Any
from shiori_sdk.lifecycle import PHASE_SLOTS, require_phase_slot

from agent.plugin_host.call_gate import PluginCallGate
from shiori_sdk.kernel import Scope

if TYPE_CHECKING:
    from agent.plugin_host.rpc import PluginRpcRegistry, RpcHandler
    from shiori_sdk.rpc import Concurrency


class PluginContributions:
    """单个插件贡献的运行时对象集合；随插件卸载整体废弃。"""

    def __init__(self) -> None:
        self.phase_modules: dict[str, list[object]] = {slot: [] for slot in PHASE_SLOTS}


def contribute_to_list[T](
    target: list[T],
    item: T,
    *,
    effects: Scope,
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

    _ = effects.effect(discard, label)


class ContributionsByPlugin[T]:
    """Each plugin's contributed objects, read back in a given plugin order.

    The storage behind a ``PluginContributionService``: a plugin's view adds to
    ``of(plugin_id)`` with ``contribute_to_list`` (so disposal withdraws it), and
    ``active`` returns what the active plugins contributed.
    """

    def __init__(self) -> None:
        self._by_plugin: dict[str, list[T]] = {}

    def of(self, plugin_id: str) -> list[T]:
        """The (live) list holding ``plugin_id``'s contributions."""
        return self._by_plugin.setdefault(plugin_id, [])

    def active(self, plugin_ids: Iterable[str]) -> list[T]:
        """The contributions of ``plugin_ids``, plugin by plugin in that order."""
        return [item for pid in plugin_ids for item in self._by_plugin.get(pid, ())]


class LifecycleCapability:
    """向 Shiori 定义的 phase 槽位贡献模块；槽位顺序语义仍由核心拥有。

    模块的 ``run`` 经过插件实例的调用闸门：代内重载会等待已进入的这一次执行，
    闸门关闭后模块直接放行 frame。
    """

    def __init__(
        self,
        contributions: PluginContributions,
        effects: Scope,
        calls: PluginCallGate,
    ) -> None:
        self._contributions = contributions
        self._effects = effects
        self._calls = calls

    def contribute(self, slot: str, modules: Sequence[object]) -> None:
        require_phase_slot(slot)
        self._effects.ensure_active(f"phase:{slot}")
        for module in modules:
            self._calls.guard_phase_module(module)
        target = self._contributions.phase_modules[slot]
        target.extend(modules)

        def remove_contributed() -> None:
            for module in modules:
                if module in target:
                    target.remove(module)

        _ = self._effects.effect(remove_contributed, f"phase:{slot}:{len(modules)}")


class RpcCapability:
    """ctx.rpc：向 ``plugin.<id>.<method>`` 命名空间登记桥接可调用方法。

    并发/准入语义复用桌面桥接的 ``MethodPolicy``；未声明时回落到保守默认
    （非只读并发、非豁免准入），由插件按需通过参数放宽。卸载/回滚时经
    Scope 反注册，使方法可调用性与插件在架状态严格同步。
    """

    def __init__(
        self,
        registry: "PluginRpcRegistry",
        effects: Scope,
        plugin_id: str,
        calls: PluginCallGate,
        event_bus: Any = None,
    ) -> None:
        self._registry = registry
        self._effects = effects
        self._plugin_id = plugin_id
        self._calls = calls
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
        from desktop_bridge.method_policy import Handler, MethodPolicy
        from shiori_sdk.rpc import Concurrency

        full_name = f"plugin.{self._plugin_id}.{name}"
        self._effects.ensure_active(f"rpc:{full_name}")
        policy = MethodPolicy(
            concurrency=concurrency or Concurrency.MUTATION,
            admission_exempt=admission_exempt,
            handler=Handler.GENERATION,
        )
        self._registry.register(
            full_name, self._plugin_id, self._calls.guard(handler), policy
        )
        _ = self._effects.effect(
            lambda: self._registry.unregister(full_name), f"rpc:{full_name}"
        )
