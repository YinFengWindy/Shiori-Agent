from __future__ import annotations

from pathlib import Path
from typing import Any, cast

from shiori_sdk.tools import Tool
from agent.tools.filesystem import EditFileTool, WriteFileTool
from agent.tools.message_lookup import FetchMessagesTool, SearchMessagesTool
from agent.tools.message_push import MessagePushTool
from agent.tools.registry import ToolRegistry
from agent.tools.shell import ShellTool, ShellTaskOutputTool, ShellTaskStopTool
from agent.tools.tool_search import ToolSearchTool


def register_common_meta_tools(
    tools: ToolRegistry,
    readonly_tools: dict[str, Tool],
    session_store: Any,
    workspace: Path,
    push_tool: MessagePushTool,
) -> None:
    """Registers the always-on meta tools; ``push_tool`` is the runtime's shared
    ``message_push`` instance, built with the role target check bound."""
    # external_allowed 标出外部上下文受限回合仍可用的内置工具（#489）。
    tools.register(
        ToolSearchTool(tools),
        always_on=True,
        risk="read-only",
        external_allowed=True,
    )
    tools.register(
        ShellTool(),
        always_on=True,
        risk="external-side-effect",
        search_hint="终端 脚本 shell sh bash pwsh PowerShell 命令",
    )
    tools.register(
        ShellTaskOutputTool(),
        always_on=True,
        risk="read-only",
        search_hint="后台任务输出 task_output 进程日志",
    )
    tools.register(
        ShellTaskStopTool(),
        always_on=True,
        risk="external-side-effect",
        search_hint="停止后台任务 task_stop 杀进程",
    )
    tools.register(
        cast(Tool, readonly_tools["web_search"]),
        always_on=True,
        risk="read-only",
        search_hint="谷歌 Bing 查资料",
        external_allowed=True,
    )
    tools.register(
        cast(Tool, readonly_tools["web_fetch"]),
        always_on=True,
        risk="read-only",
        search_hint="读取网址 浏览网页",
        external_allowed=True,
    )
    tools.register(
        cast(Tool, readonly_tools["read_file"]),
        always_on=True,
        risk="read-only",
    )
    tools.register(
        cast(Tool, readonly_tools["list_dir"]),
        always_on=True,
        risk="read-only",
        search_hint="ls 查看目录",
    )
    tools.register(
        FetchMessagesTool(session_store, workspace),
        always_on=True,
        risk="read-only",
        search_hint="消息回溯 按ID查对话原文 source_ref",
        external_allowed=True,
    )
    tools.register(
        SearchMessagesTool(session_store, workspace),
        always_on=True,
        risk="read-only",
        search_hint="你之前说 聊过什么 历史对话",
        external_allowed=True,
    )
    tools.register(
        push_tool,
        always_on=True,
        risk="external-side-effect",
    )
    tools.register(
        WriteFileTool(),
        always_on=True,
        risk="write",
    )
    tools.register(
        EditFileTool(),
        always_on=True,
        risk="write",
    )
