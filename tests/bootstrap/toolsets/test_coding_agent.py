from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

from agent.tools.registry import ToolRegistry
from bootstrap.toolsets.coding_agent import CodingAgentToolsetProvider
from bootstrap.toolsets.protocol import ToolsetDeps


def test_disabled_feature_registers_no_tool(tmp_path: Path) -> None:
    registry = ToolRegistry()
    result = CodingAgentToolsetProvider().register(
        registry,
        ToolsetDeps(
            config=SimpleNamespace(coding_agents=SimpleNamespace(enabled=False)),
            workspace=tmp_path,
        ),
    )

    assert result.tool_names == []
    assert not registry.has_tool("coding_agent")


def test_enabled_feature_registers_orchestrator_tool(tmp_path: Path) -> None:
    registry = ToolRegistry()
    orchestrator = object()
    result = CodingAgentToolsetProvider().register(
        registry,
        ToolsetDeps(
            config=SimpleNamespace(coding_agents=SimpleNamespace(enabled=True)),
            workspace=tmp_path,
            coding_orchestrator=orchestrator,
        ),
    )

    assert result.tool_names == ["coding_agent"]
    assert result.extras["coding_orchestrator"] is orchestrator
