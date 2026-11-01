"""The drift run's own tool registry.

It adds the progress-description field and drops it before execution, the
same way the host registry does, and does not import that registry.
"""

from __future__ import annotations

import logging
from copy import deepcopy
from typing import Any

from shiori_sdk.tools import TOOL_ATTACHMENT_SCOPE_KEY, Tool, ToolResult

logger = logging.getLogger(__name__)

_PROGRESS_DESCRIPTION_FIELD = "description"
_PROGRESS_DESCRIPTION_SCHEMA: dict[str, str] = {
    "type": "string",
    "description": (
        "用 5-12 个字说明这次工具调用的意图，只写给用户看的短语。"
        "不要复述工具名，不要粘贴长参数。例如：查看目录、读取配置、搜索健康数据。"
    ),
}


def _schema_properties(parameters: dict[str, Any]) -> dict[str, Any]:
    raw_properties = parameters.get("properties")
    if isinstance(raw_properties, dict):
        return raw_properties
    properties: dict[str, Any] = {}
    parameters["properties"] = properties
    return properties


def _tool_defines_parameter(tool: Tool, name: str) -> bool:
    parameters: dict[str, Any] = tool.parameters or {}
    properties = parameters.get("properties")
    return isinstance(properties, dict) and name in properties


def _with_progress_description(schema: dict[str, Any], tool: Tool) -> dict[str, Any]:
    cloned = deepcopy(schema)
    function = cloned.get("function")
    if not isinstance(function, dict):
        return cloned
    parameters = function.get("parameters")
    if not isinstance(parameters, dict):
        return cloned
    if _tool_defines_parameter(tool, _PROGRESS_DESCRIPTION_FIELD):
        return cloned
    properties = _schema_properties(parameters)
    properties[_PROGRESS_DESCRIPTION_FIELD] = dict(_PROGRESS_DESCRIPTION_SCHEMA)
    required = parameters.get("required")
    if isinstance(required, list):
        if _PROGRESS_DESCRIPTION_FIELD not in required:
            required.append(_PROGRESS_DESCRIPTION_FIELD)
    else:
        parameters["required"] = [_PROGRESS_DESCRIPTION_FIELD]
    return cloned


class LocalToolRegistry:
    """Registers drift tools and runs them with the progress field stripped."""

    def __init__(self) -> None:
        self._tools: dict[str, Tool] = {}

    def register(self, tool: Tool, *, risk: str = "read-only") -> None:
        """Register ``tool``. ``risk`` is recorded only as the caller's label."""
        del risk
        self._tools[tool.name] = tool

    def has_tool(self, name: str) -> bool:
        return name in self._tools

    def get_schemas(self) -> list[dict[str, Any]]:
        """OpenAI function schemas in registration order, with the progress field."""
        return [
            _with_progress_description(tool.to_schema(), tool)
            for tool in self._tools.values()
        ]

    async def execute(self, name: str, arguments: dict[str, Any]) -> str | ToolResult:
        """Run ``name``. An unknown tool or a raised error becomes a text result."""
        tool = self._tools.get(name)
        if tool is None:
            return f"工具 '{name}' 不存在"
        merged = dict(arguments)
        merged.pop(TOOL_ATTACHMENT_SCOPE_KEY, None)
        if not _tool_defines_parameter(tool, _PROGRESS_DESCRIPTION_FIELD):
            merged.pop(_PROGRESS_DESCRIPTION_FIELD, None)
        try:
            return await tool.execute(**merged)
        except Exception as exc:
            logger.error("工具 %s 执行出错: %s", name, exc, exc_info=True)
            return f"工具执行出错: {exc}"
