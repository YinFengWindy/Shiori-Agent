"""插件 RPC 命名空间注册表：内核持有，宿主分发器/路由经此解析 plugin.<id>.<method>。

策略类型（``MethodPolicy`` / ``Concurrency`` / ``Handler``）直接复用桌面桥接
既有定义，避免在内核与桥接两侧各维护一套并发/准入语义。本模块只把它当类型
标注使用（配合 ``from __future__ import annotations`` 不在运行时求值），不在
模块顶层实际导入 ``desktop_bridge``，避免核心插件运行时在加载期就被迫拉入
桌面桥接的完整依赖链。
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from agent.plugin_host.communication import PluginCommunication
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from desktop_bridge.method_policy import MethodPolicy

# handler 签名：接收 payload，返回结果 dict 或 None（None 视为空结果）
RpcHandler = Callable[[dict[str, Any]], Awaitable[dict[str, Any] | None]]


@dataclass(frozen=True)
class _RpcEntry:
    """单条已注册 RPC：来源插件、处理函数与调度/准入策略。"""

    plugin_id: str
    handler: RpcHandler
    policy: MethodPolicy


class PluginRpcRegistry:
    """维护 ``plugin.<id>.<method>`` 全名 -> (plugin_id, handler, policy)。

    生命周期与单个 runtime generation 的 PluginKernel 一一对应；插件卸载或
    加载失败回滚时经 EffectScope 反注册（见 capabilities.RpcCapability），
    保证桥接分发器看到的可调用方法与插件的在架状态严格同步。
    """

    def __init__(self) -> None:
        self._entries: dict[str, _RpcEntry] = {}
        self.communication = PluginCommunication(self)

    def register(
        self,
        full_name: str,
        plugin_id: str,
        handler: RpcHandler,
        policy: MethodPolicy,
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

    def policy_for(self, full_name: str) -> MethodPolicy | None:
        """Returns the declared dispatch policy, or None when unregistered."""
        entry = self._entries.get(full_name)
        return None if entry is None else entry.policy
