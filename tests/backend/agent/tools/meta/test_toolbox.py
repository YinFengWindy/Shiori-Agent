from pathlib import Path
from typing import Any, cast

from agent.tools.filesystem import ListDirTool, ReadFileTool
from agent.tools.meta import (
    META_TOOLBOX_NAMES,
    build_meta_toolbox_prompt,
    register_common_meta_tools,
)
from agent.tools.message_push import MessagePushTool
from agent.tools.registry import ToolRegistry
from agent.tools.web_fetch import WebFetchTool
from agent.tools.web_search import WebSearchTool
from tests.support.push import allow_every_role_target


def test_meta_toolbox_prompt_contains_grouped_overview():
    prompt = build_meta_toolbox_prompt()

    assert "MetaToolBox" in prompt
    assert "[Read]" in prompt
    assert "recall_memory" in prompt
    assert "message_push" in prompt
    assert "write_file" in prompt


def test_register_meta_tool_helpers_mark_expected_tools_always_on():
    tools = ToolRegistry()
    readonly_tools = {
        "web_search": WebSearchTool(),
        "web_fetch": WebFetchTool(requester=cast(Any, object())),
        "read_file": ReadFileTool(),
        "list_dir": ListDirTool(),
    }

    push_tool = MessagePushTool(role_target_validator=allow_every_role_target)
    register_common_meta_tools(
        tools,
        readonly_tools,
        session_store=object(),
        workspace=Path("."),
        push_tool=push_tool,
    )

    always_on = tools.get_always_on_names()
    assert tools.get_tool("message_push") is push_tool
    # memorize / recall_memory / forget_memory 由 default_memory 注册，不在这里。
    assert (
        set(META_TOOLBOX_NAMES) - {"memorize", "recall_memory", "forget_memory"}
        <= always_on
    )
    # 外部上下文受限回合只放行这些内置工具；记忆读写、命令、文件、推送一律不放行。
    external_allowed = {
        name for name in tools.get_registered_names() if tools.is_external_allowed(name)
    }
    assert external_allowed == {
        "tool_search",
        "web_search",
        "web_fetch",
        "fetch_messages",
        "search_messages",
    }
