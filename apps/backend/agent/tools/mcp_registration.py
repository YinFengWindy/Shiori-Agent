"""Dynamic MCP tools use the owning plugin's existing admission and scope."""

from shiori_sdk.tools import Tool
from agent.plugin_host.core_keys import PluginBinding
from agent.tools.registry import ToolRegistry


class HostMcpToolRegistration:
    """Per-plugin binder over the generation's tool registry."""

    def __init__(self, registry: ToolRegistry) -> None:
        self._registry = registry

    def for_plugin(self, binding: PluginBinding) -> "McpRegistration":
        """Bind dynamic registration to the same gate as ordinary plugin tools."""
        return McpRegistration(self._registry, binding)


class McpRegistration:
    """Owns only this activation's tool objects; cleanup cannot remove successors."""

    def __init__(self, registry: ToolRegistry, binding: PluginBinding):
        self._registry, self._binding = registry, binding
        self._owned: dict[str, Tool] = {}
        binding.scope.effect(self.close, "mcp-tools")

    def add(
        self, tool: Tool, *, server: str, risk: str = "external-side-effect"
    ) -> None:
        """Register metadata and admission on the exact exported wrapper object."""
        self._binding.scope.ensure_active(f"mcp:{tool.name}")
        if self._registry.get_tool(tool.name) not in (None, self._owned.get(tool.name)):
            raise ValueError("MCP tool name already registered")
        self._binding.calls.guard_tool(tool)
        try:
            self._registry.register(
                tool, risk=risk, source_type="mcp", source_name=server
            )
        except Exception:
            if self._registry.get_tool(tool.name) is tool:
                self._registry.unregister(tool.name)
            raise
        self._owned[tool.name] = tool

    def remove(self, name: str) -> None:
        """Remove this activation's current registration only."""
        tool = self._owned.pop(name, None)
        if tool is not None and self._registry.get_tool(name) is tool:
            self._registry.unregister(name)

    def close(self) -> None:
        """Drop all remaining registrations on scope disposal."""
        for name in tuple(self._owned):
            self.remove(name)
