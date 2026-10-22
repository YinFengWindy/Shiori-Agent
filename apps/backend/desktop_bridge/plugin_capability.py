"""The ``rpc`` plugin capability: bridge-callable plugin methods (#901 P2).

``PluginRpc`` is the ``host.rpc`` core service over the generation's
``PluginRpcRegistry``; each plugin's ``RpcCapability`` registers methods under
``plugin.<id>.`` with the bridge's ``MethodPolicy`` and pushes plugin events to
the renderer through the event bus.
"""

from __future__ import annotations

from typing import Any

from shiori_sdk.rpc import Concurrency

from agent.plugin_host.bridge_events import PluginBridgeEvent
from agent.plugin_host.communication import communication_name
from agent.plugin_host.core_keys import PluginBinding
from agent.plugin_host.rpc import PluginRpcRegistry, RpcHandler
from bus.event_bus import EventBus
from desktop_bridge.method_policy import Handler, MethodPolicy


class PluginRpc:
    """The ``host.rpc`` core service of one plugin kernel generation."""

    def __init__(
        self, registry: PluginRpcRegistry[MethodPolicy], event_bus: EventBus
    ) -> None:
        self._registry = registry
        self._event_bus = event_bus

    def for_plugin(self, binding: PluginBinding) -> RpcCapability:
        """The RPC capability of the plugin ``binding`` describes."""
        return RpcCapability(self._registry, binding, self._event_bus)


class RpcCapability:
    """ctx.rpc：向 ``plugin.<id>.<method>`` 命名空间登记桥接可调用方法。

    并发/准入语义复用桌面桥接的 ``MethodPolicy``；未声明时回落到保守默认
    （非只读并发、非豁免准入），由插件按需通过参数放宽。卸载/回滚时经
    Scope 反注册，使方法可调用性与插件在架状态严格同步。
    """

    def __init__(
        self,
        registry: PluginRpcRegistry[MethodPolicy],
        binding: PluginBinding,
        event_bus: EventBus,
    ) -> None:
        self._registry = registry
        self._effects = binding.scope
        self._plugin_id = binding.plugin_id
        self._calls = binding.calls
        self._event_bus = event_bus

    async def emit(self, name: str, payload: dict[str, Any]) -> bool:
        """Reports transport delivery, not individual renderer consumption."""
        self._effects.ensure_active(f"event:{name}")
        communication_name(name)
        event = PluginBridgeEvent(
            f"plugin.{self._plugin_id}.{name}", payload, self._registry
        )
        await self._event_bus.emit(event)
        return event.dispatched

    def register(
        self,
        name: str,
        handler: RpcHandler,
        *,
        concurrency: Concurrency | None = None,
        admission_exempt: bool = False,
    ) -> None:
        """Serves ``plugin.<id>.<name>`` with ``handler`` until the plugin stops."""
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
