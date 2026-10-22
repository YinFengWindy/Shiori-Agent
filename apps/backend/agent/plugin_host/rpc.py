"""插件 RPC 命名空间注册表：宿主分发器/路由经此解析 plugin.<id>.<method>。

每个 runtime generation 由 bootstrap 创建一份，作为 ``host.bridge`` 核心服务
提供给内核（#901 P2）。注册表不关心策略的具体类型 ``P``：桌面桥接登记并读取
自己的 ``MethodPolicy``，内核只负责撤回。
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from agent.plugin_host.communication import PluginCommunication
from agent.plugin_host.services import PluginServiceRegistry
from typing import Any

# handler 签名：接收 payload，返回结果 dict 或 None（None 视为空结果）
RpcHandler = Callable[[dict[str, Any]], Awaitable[dict[str, Any] | None]]


@dataclass(frozen=True)
class _RpcEntry[P]:
    """单条已注册 RPC：来源插件、处理函数与调度/准入策略。"""

    plugin_id: str
    handler: RpcHandler
    policy: P


class PluginRpcRegistry[P]:
    """维护 ``plugin.<id>.<method>`` 全名 -> (plugin_id, handler, policy)。

    生命周期与单个 runtime generation 的 PluginKernel 一一对应；插件卸载或
    加载失败回滚时经插件 Scope 反注册（见 ``desktop_bridge.plugin_capability``
    的 ``RpcCapability``），保证桥接分发器看到的可调用方法与插件的在架状态
    严格同步。``event_bus`` 是 renderer communication 推送事件用的总线。
    """

    def __init__(self, event_bus: Any) -> None:
        self._entries: dict[str, _RpcEntry[P]] = {}
        self.services = PluginServiceRegistry()
        self.communication = PluginCommunication(self, event_bus)

    def register(
        self,
        full_name: str,
        plugin_id: str,
        handler: RpcHandler,
        policy: P,
    ) -> None:
        """登记一个全名方法；同名重复注册视为编程错误，直接报错。"""
        if full_name in self._entries:
            raise ValueError(f"RPC 方法已注册: {full_name}")
        self._entries[full_name] = _RpcEntry(plugin_id, handler, policy)

    def unregister(self, full_name: str) -> None:
        """移除一个方法；不存在时静默忽略，保持处置幂等。"""
        self._entries.pop(full_name, None)

    def __contains__(self, full_name: str) -> bool:
        return full_name in self._entries

    def resolve(self, full_name: str) -> tuple[str, RpcHandler] | None:
        """Returns the owning plugin id and handler, or None when unregistered."""
        entry = self._entries.get(full_name)
        return None if entry is None else (entry.plugin_id, entry.handler)

    def policy_for(self, full_name: str) -> P | None:
        """Returns the declared dispatch policy, or None when unregistered."""
        entry = self._entries.get(full_name)
        return None if entry is None else entry.policy
