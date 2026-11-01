"""Host file tools a Drift run uses, confined to the role's drift directory."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from agent.proactive_host.tools import require_checked_tool
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


def drift_dir(workspace: Path, role_id: str) -> Path:
    """``roles/<role_id>/drift``. A role id that is not one path segment raises."""
    clean = str(role_id or "").strip()
    if not clean or clean in {".", ".."} or Path(clean).name != clean:
        raise ValueError(f"非法角色 id: {role_id!r}")
    return workspace / "roles" / clean / "drift"


async def run_drift_file_tool(
    workspace: Path,
    role_id: str,
    name: str,
    arguments: dict[str, Any],
) -> str | ToolResult:
    """Run file tool ``name`` for ``role_id``'s Drift.

    Only inside an ``execute_tool`` invoker for that tool name. Writes and
    edits stay inside the drift directory. A read of a relative path stays
    there too; an absolute (or empty) path is read as given, as Drift always
    could.
    """
    require_checked_tool(name)
    tool_type = _FILE_TOOLS.get(name)
    if tool_type is None:
        raise LookupError(f"宿主文件工具不存在: {name}")
    root: Path | None = drift_dir(workspace, role_id)
    if name == "read_file":
        raw = str(arguments.get("path") or "").strip()
        if not raw or Path(raw).expanduser().is_absolute():
            root = None
    tool = tool_type(allowed_dir=root)
    try:
        return await tool.execute(**arguments)
    except Exception as exc:
        return f"工具执行出错: {exc}"
