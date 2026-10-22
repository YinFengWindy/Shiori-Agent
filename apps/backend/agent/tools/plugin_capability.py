"""The ``tools`` plugin capability: plugin tools registered into the host ``ToolRegistry``.

``PluginTools`` is the ``host.tools`` core service (#901 P2); each plugin gets
its own ``ToolsCapability`` view, scoped to that plugin's lifetime.
"""

from __future__ import annotations

from shiori_sdk.tools import Tool

from agent.plugin_host.call_gate import PluginCallGate
from agent.plugin_host.capabilities import PluginContributions
from agent.plugin_host.core_keys import PluginBinding
from agent.tools.registry import ToolRegistry
from shiori_sdk.kernel import Scope


class PluginTools:
    """The ``host.tools`` core service over one ``ToolRegistry``."""

    def __init__(self, registry: ToolRegistry) -> None:
        self._registry = registry

    def for_plugin(self, binding: PluginBinding) -> ToolsCapability:
        """The tools capability of the plugin ``binding`` describes."""
        return ToolsCapability(
            self._registry,
            binding.scope,
            binding.contributions,
            binding.plugin_id,
            binding.calls,
        )


class ToolsCapability:
    """注册插件工具到 ToolRegistry；卸载时通过 effect 反注册。

    每个工具的执行都经过插件实例的调用闸门，代内重载据此排空在途调用。
    """

    def __init__(
        self,
        registry: ToolRegistry,
        effects: Scope,
        contributions: PluginContributions,
        plugin_id: str,
        calls: PluginCallGate,
    ) -> None:
        self._registry = registry
        self._effects = effects
        self._contributions = contributions
        self._plugin_id = plugin_id
        self._calls = calls

    def register(
        self,
        tool: Tool,
        *,
        risk: str = "read-write",
        always_on: bool = False,
        search_hint: str | None = None,
        external_allowed: bool = False,
    ) -> None:
        """注册插件工具。

        external_allowed: 显式声明外部上下文（群聊、陌生私聊）里非用户本人发起的
        回合也能使用此工具；默认不可用。
        """
        name = str(tool.name)
        self._effects.ensure_active(f"tool:{name}")
        self._calls.guard_tool(tool)
        self._registry.register(
            tool,
            risk=risk,
            always_on=always_on,
            search_hint=search_hint,
            source_type="plugin",
            external_allowed=external_allowed,
            source_name=self._plugin_id,
        )
        # 工具除了从贡献清单移除，还要反注册出 ToolRegistry，故不复用列表 helper
        self._contributions.tool_names.append(name)
        _ = self._effects.effect(lambda: self._unregister(name), f"tool:{name}")

    def _unregister(self, name: str) -> None:
        self._registry.unregister(name)
        if name in self._contributions.tool_names:
            self._contributions.tool_names.remove(name)

    def get_tool(self, name: str) -> Tool | None:
        """Looks up another tool by name (e.g. to invoke it directly).

        Read-only passthrough to the underlying ``ToolRegistry`` — unlike
        ``register``, there is no lifecycle to own here, so this does not need
        a ``Scope`` entry. Registration itself must still go through
        ``register`` above so the tool is reclaimed on unload; this only lets
        a plugin look up and call a tool (its own or another's).
        """
        return self._registry.get_tool(name)

    def get_context(self) -> dict[str, str]:
        """Returns the current tool-call context (read-only passthrough)."""
        return self._registry.get_context()
