"""按引擎 tool_profile 注册 memorize、forget_memory、recall_memory。"""

from __future__ import annotations

from typing import Any, cast

from shiori_sdk.memory.engine import MemoryEngine, MemoryToolSpec
from shiori_sdk.tools import Tool, ToolsCapability

from .forget_memory import ForgetMemoryTool
from .memorize import MemorizeTool
from .recall_memory import RecallMemoryTool


class _MemorySignalTool(Tool):
    name = "memory_signal"
    description = "由当前 memory engine 的 tool_profile 注入工具描述。"
    parameters = {"type": "object", "properties": {}, "required": []}

    def __init__(
        self,
        memory: MemoryEngine,
        spec: MemoryToolSpec,
    ) -> None:
        if not spec.name:
            raise ValueError("自定义 memory 工具缺少 name")
        self._memory = memory
        self._spec = spec
        self.name = spec.name
        self.description = spec.description
        self.parameters = spec.parameters

    async def execute(
        self,
        **kwargs: Any,
    ) -> str:
        return "已记录。"


def register_memory_meta_tools(
    tools: ToolsCapability,
    engine: MemoryEngine,
) -> None:
    """按引擎 ``tool_profile`` 把记忆工具注册到 ``tools``。

    同名或非法工具名直接失败，不覆盖已有工具。
    """
    profile = engine.tool_profile()
    if profile.memorize is not None:
        _register_memory_tool(
            tools,
            _build_tool(engine, profile.memorize, MemorizeTool),
            risk=profile.memorize.risk,
            search_hint=profile.memorize.search_hint or None,
        )
    if profile.forget is not None:
        _register_memory_tool(
            tools,
            _build_tool(engine, profile.forget, ForgetMemoryTool),
            risk=profile.forget.risk,
            search_hint=profile.forget.search_hint or None,
        )
    if profile.recall is not None:
        _register_memory_tool(
            tools,
            _build_tool(engine, profile.recall, RecallMemoryTool),
            risk=profile.recall.risk,
            search_hint=profile.recall.search_hint or None,
        )
    for spec in profile.tools:
        _register_memory_tool(
            tools,
            _build_tool(engine, spec, _MemorySignalTool),
            risk=spec.risk,
            search_hint=spec.search_hint or None,
        )


def _register_memory_tool(
    tools: ToolsCapability,
    tool: Tool,
    *,
    risk: str,
    search_hint: str | None = None,
) -> None:
    _validate_memory_tool_name(tool.name)
    if tools.get_tool(tool.name) is not None:
        raise ValueError(f"memory 工具重复注册: {tool.name}")
    tools.register(
        tool,
        always_on=True,
        risk=risk,
        search_hint=search_hint,
    )


def _build_tool(engine: MemoryEngine, spec: MemoryToolSpec, default_cls: type) -> Tool:
    cls = spec.tool_class if spec.tool_class is not None else default_cls
    return cast(Tool, cls(engine, spec))


def _validate_memory_tool_name(name: str) -> None:
    if not name or not name[0].isalpha():
        raise ValueError(f"memory 工具名非法: {name}")
    if any(not (char.islower() or char.isdigit() or char == "_") for char in name):
        raise ValueError(f"memory 工具名非法: {name}")
