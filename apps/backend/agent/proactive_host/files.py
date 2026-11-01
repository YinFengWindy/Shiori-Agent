"""Host file tools the proactive plugin runs without importing them."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from agent.tools.filesystem import EditFileTool, ReadFileTool, WriteFileTool
from shiori_sdk.tools import ToolResult

_FILE_TOOLS = {
    "read_file": ReadFileTool,
    "write_file": WriteFileTool,
    "edit_file": EditFileTool,
}


def file_tool_schema(name: str) -> dict[str, Any]:
    """Schema of a host file tool. Unknown names raise ``KeyError``."""
    return _FILE_TOOLS[name]().to_schema()


async def run_restricted_file_tool(
    name: str,
    arguments: dict[str, Any],
    *,
    root: str | None,
) -> str | ToolResult:
    """Run ``name`` jailed to ``root``, or unrestricted when ``root`` is None."""
    tool_type = _FILE_TOOLS.get(name)
    if tool_type is None:
        return f"工具 '{name}' 不存在"
    allowed = Path(root) if root else None
    tool = tool_type(allowed_dir=allowed)
    try:
        return await tool.execute(**arguments)
    except Exception as exc:
        return f"工具执行出错: {exc}"
