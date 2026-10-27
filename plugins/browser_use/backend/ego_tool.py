"""Provider-specific structured ego operations with host-bound task identity."""

from typing import Any

from shiori_sdk.tools import Tool, ToolResult

from .browser import BrowserSessions

_PAGE = {
    "type": "string",
    "description": "当前角色 Space 中的页面标签，例如 p1；从工具结果读取。",
}
_STRING = {"type": "string"}
_ACTION = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "action": {
            "type": "string",
            "enum": ["click", "fill", "press", "select", "hover", "scroll", "wait"],
        },
        "selector": {
            "type": "string",
            "description": "来自当前页面快照的 @ref、loc 或 CSS。",
        },
        "text": _STRING,
        "key": _STRING,
        "values": {"type": "array", "items": _STRING},
        "x": {"type": "number"},
        "y": {"type": "number"},
        "delta_x": {"type": "number"},
        "delta_y": {"type": "number"},
    },
    "required": ["action"],
}

_SPECS = {
    "open": (
        "在当前角色的 ego Space 打开网页，返回快照。",
        {"url": _STRING, "page": _PAGE},
        ["url"],
    ),
    "snapshot": (
        "读取当前页面快照。页面改变或引用失效后重新观察。",
        {"page": _PAGE, "full_page": {"type": "boolean"}},
        [],
    ),
    "actions": (
        "依序执行已观察页面上的动作并返回最终快照；fill 需要 text，press 需要 key，select 需要 values，scroll 需要 x/y/delta_y，其他动作需要 selector。",
        {
            "page": _PAGE,
            "actions": {
                "type": "array",
                "items": _ACTION,
                "minItems": 1,
                "maxItems": 32,
            },
        },
        ["actions"],
    ),
    "tabs": (
        "列出当前 Space 标签页、创建空白页或关闭指定受管页面。新页面标签从结果读取。",
        {"action": {"type": "string", "enum": ["list", "new", "close"]}, "page": _PAGE},
        ["action"],
    ),
    "screenshot": (
        "返回当前角色页面的原始 PNG 图片。",
        {"page": _PAGE, "full_page": {"type": "boolean"}},
        [],
    ),
    "handoff": (
        "把当前任务交给用户完成登录、验证或人工操作，随后等待用户确认。",
        {},
        [],
    ),
    "resume": (
        "仅在用户确认人工操作完成后，恢复本角色先前交出的任务并读取快照。",
        {"page": _PAGE},
        [],
    ),
    "close": (
        "结束本角色的 ego 浏览任务；保留用户页面、其他角色任务和 ego 浏览器。",
        {},
        [],
    ),
}


def ego_tools(sessions: BrowserSessions) -> list["EgoTool"]:
    """Expose only the ego provider's controlled TaskSpace/Page operations."""
    return [EgoTool(sessions, name) for name in _SPECS]


class EgoTool(Tool):
    """The model supplies page actions; Space and filesystem paths stay host-owned."""

    context_precedence = frozenset({"role_id"})

    def __init__(self, sessions: BrowserSessions, operation: str) -> None:
        self._sessions, self._operation = sessions, operation

    @property
    def name(self) -> str:
        return "ego_browser_" + self._operation

    @property
    def description(self) -> str:
        return "[Browser Use / ego(lite)] " + _SPECS[self._operation][0]

    @property
    def parameters(self) -> dict[str, Any]:
        _, properties, required = _SPECS[self._operation]
        return {
            "type": "object",
            "properties": properties,
            "required": required,
            "additionalProperties": False,
        }

    async def execute(self, *, role_id: str = "", **kwargs: Any) -> str | ToolResult:
        """Validate model data before any browser side effects."""
        if {
            "space",
            "space_id",
            "spaceId",
            "profile",
            "path",
            "root",
            "script",
            "code",
        }.intersection(kwargs):
            raise ValueError("Browser Use Space、脚本和输出路径由宿主管理")
        arguments = {
            key: value
            for key, value in kwargs.items()
            if key in self.parameters["properties"]
        }
        errors = self.validate_params(arguments)
        if (
            self._operation == "tabs"
            and arguments.get("action") == "close"
            and not arguments.get("page")
        ):
            errors.append("关闭标签页必须提供 page")
        if self._operation == "actions" and not errors:
            if not 1 <= len(arguments["actions"]) <= 32:
                errors.append("每批动作数量必须在 1 到 32 之间")
            for action in arguments["actions"]:
                if set(action) - set(_ACTION["properties"]):
                    errors.append("动作包含不支持的字段")
                needed = {
                    "fill": ("selector", "text"),
                    "press": ("selector", "key"),
                    "select": ("selector", "values"),
                    "scroll": ("x", "y", "delta_y"),
                }.get(action["action"], ("selector",))
                errors.extend(
                    f"{action['action']} 缺少 {key}"
                    for key in needed
                    if key not in action
                )
        if errors:
            raise ValueError("；".join(errors))
        return await self._sessions.call(role_id, self.name, arguments)
