"""Group tools join the #489 whitelist as declared: lookup yes, listening switch no."""

from __future__ import annotations

from pathlib import Path

from agent.core.passive_turn.helpers import turn_tool_names
from agent.tools.registry import ToolRegistry
from bootstrap.toolsets.groups import register_group_tools
from session.manager import SessionManager


def test_a_group_member_turn_gets_the_lookup_but_not_the_listening_switch(
    tmp_path: Path,
) -> None:
    manager = SessionManager(tmp_path)
    tools = ToolRegistry()
    _ = register_group_tools(tools, tmp_path, manager, manifests=())

    # 外部上下文里群友触发的回合（受限回合）。
    restricted = turn_tool_names(
        tools, None, disabled=frozenset(), external_restricted=True
    )

    assert restricted == ["lookup_member"]
    assert tools.external_denial("set_group_listening", {"enabled": True})
