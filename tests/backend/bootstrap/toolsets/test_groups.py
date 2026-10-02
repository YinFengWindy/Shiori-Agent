"""Only member lookup joins the external whitelist; group context stays restricted."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from agent.core.passive_turn.helpers import turn_tool_names
from agent.tools.external_access import EXTERNAL_TOOL_DENIED, external_tools_restricted
from agent.tools.registry import ToolRegistry
from agent.tools.tool_search import ToolSearchTool
from bootstrap.toolsets.groups import register_group_tools
from conversation.context_scope import ContextView, UserContextThreads
from shiori_sdk.channels.message_source import MessageSource
from core.memory.group_environment import GroupEnvironment
from session.manager import SessionManager


@pytest.mark.asyncio
@pytest.mark.parametrize("sender_is_user", [False, True])
async def test_group_tools_follow_the_external_sender_permission(
    tmp_path: Path, sender_is_user: bool
) -> None:
    manager = SessionManager(tmp_path)
    tools = ToolRegistry()
    _ = register_group_tools(
        tools,
        tmp_path,
        manager,
        manifests=(),
        group_environment=GroupEnvironment(tmp_path, manager.conversation_store),
    )

    restricted = external_tools_restricted(
        ContextView(
            scope="external",
            user_threads=UserContextThreads("mira", frozenset()),
        ),
        MessageSource(sender_is_user=sender_is_user),
    )
    assert restricted is not sender_is_user
    names = turn_tool_names(
        tools, None, disabled=frozenset(), external_restricted=restricted
    )
    schemas = tools.get_schemas(names, external_only=restricted)
    for name in ("lookup_group_context", "update_group_context"):
        assert (name in [s["function"]["name"] for s in schemas]) is sender_is_user
        assert (
            name in tools.get_deferred_names(external_only=restricted)["builtin"]
        ) is sender_is_user
        assert tools.external_denial(name, {}) == EXTERNAL_TOOL_DENIED
    if restricted:
        assert names == ["lookup_member"]
    assert tools.external_denial("set_group_listening", {"enabled": True})

    search = ToolSearchTool(tools)
    for query, name in (
        ("查其他群的群笔记", "lookup_group_context"),
        ("群摘要", "lookup_group_context"),
        ("select:lookup_group_context", "lookup_group_context"),
        ("改群笔记", "update_group_context"),
        ("改群摘要", "update_group_context"),
        ("select:update_group_context", "update_group_context"),
    ):
        result = json.loads(
            await search.execute(query=query, external_tools_only=restricted)
        )
        assert (name in result["unlocked"]) is sender_is_user
