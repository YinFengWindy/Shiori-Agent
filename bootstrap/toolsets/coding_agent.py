"""Bootstrap provider for the optional Coding Agent toolset."""

from __future__ import annotations

from agent.tools.coding_agent import CodingAgentTool

from .protocol import ToolsetDeps, ToolsetProvider, build_registration_result


class CodingAgentToolsetProvider(ToolsetProvider):
    """Register Coding Agent only when the feature is explicitly enabled."""

    def register(self, registry, deps: ToolsetDeps):
        before = set(registry.get_registered_names())
        config = deps.config
        if config is None or not config.coding_agents.enabled:
            return build_registration_result(
                registry=registry,
                source_name="coding_agent",
                before=before,
            )
        if deps.coding_orchestrator is None:
            raise ValueError("coding_agent toolset 缺少 CodingAgentOrchestrator")
        registry.register(
            CodingAgentTool(deps.coding_orchestrator),
            always_on=True,
            risk="external-side-effect",
            search_hint="Codex Claude Code 编程 仓库 方案 实现 审查",
        )
        return build_registration_result(
            registry=registry,
            source_name="coding_agent",
            before=before,
            extras={"coding_orchestrator": deps.coding_orchestrator},
        )
