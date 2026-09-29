import logging
from contextvars import ContextVar
from collections.abc import Iterable, Set as AbstractSet
from copy import deepcopy
from dataclasses import dataclass
from typing import Any, TypedDict, cast

from agent.tools.base import Tool, ToolResult
from agent.tools.external_access import EXTERNAL_TOOL_DENIED, ExternalArgumentLimit
from agent.tools.search_backend import KeywordSearchBackend, SearchBackend

logger = logging.getLogger(__name__)

# 元工具（不参与搜索结果，也不出现在 deferred 工具目录里）
_META_TOOLS: frozenset[str] = frozenset({"tool_search"})
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
        return cast(dict[str, Any], raw_properties)
    properties: dict[str, Any] = {}
    parameters["properties"] = properties
    return properties


def _tool_defines_parameter(tool: Tool, name: str) -> bool:
    parameters: dict[str, Any] = tool.parameters or {}
    properties = parameters.get("properties")
    return isinstance(properties, dict) and name in properties


def _with_progress_description(schema: dict[str, Any], tool: Tool) -> dict[str, Any]:
    cloned = cast(dict[str, Any], deepcopy(schema))
    function = cloned.get("function")
    if not isinstance(function, dict):
        return cloned
    function = cast(dict[str, Any], function)
    parameters = function.get("parameters")
    if not isinstance(parameters, dict):
        return cloned
    parameters = cast(dict[str, Any], parameters)
    if _tool_defines_parameter(tool, _PROGRESS_DESCRIPTION_FIELD):
        return cloned
    properties = _schema_properties(parameters)
    properties[_PROGRESS_DESCRIPTION_FIELD] = dict(_PROGRESS_DESCRIPTION_SCHEMA)
    required = parameters.get("required")
    if isinstance(required, list):
        if _PROGRESS_DESCRIPTION_FIELD not in required:
            cast(list[Any], required).append(_PROGRESS_DESCRIPTION_FIELD)
    else:
        parameters["required"] = [_PROGRESS_DESCRIPTION_FIELD]
    return cloned


class DeferredToolNames(TypedDict):
    """``get_deferred_names`` 的结果：未加载 schema 的工具名，按来源分组。"""

    builtin: list[str]
    mcp: dict[str, list[str]]


# ── ToolMeta ──────────────────────────────────────────────────────────────────


@dataclass
class ToolMeta:
    risk: str = "read-only"  # "read-only" | "write" | "external-side-effect"
    always_on: bool = False
    # 可选：3–10 词短语，补充工具名和描述中没有的别名或口语化表达。
    # 不需要重复名称或描述里已有的词——搜索后端自动索引 name + description。
    search_hint: str | None = None
    # 注册方显式声明：外部上下文里非用户本人发起的回合也能使用此工具（#489）。
    # 未声明即不可用，所以以后新增的工具默认被外部回合排除。
    external_allowed: bool = False
    # 可选：外部可用工具在受限回合里的参数限制（#522），None 表示不限参数。
    external_limit: ExternalArgumentLimit | None = None


# ── ToolDocument ──────────────────────────────────────────────────────────────


@dataclass
class ToolDocument:
    """工具的索引态视图，派生自 Tool + ToolMeta，供搜索后端使用。

    搜索后端自动索引：name、description。
    search_hint 是可选补充，仅在名称和描述无法覆盖某些口语别名时填写。
    """

    name: str
    description: str
    risk: str
    always_on: bool
    search_hint: str | None
    source_type: str  # "builtin" | "mcp" | "plugin"
    source_name: str  # mcp server 名，builtin 为空字符串

    @classmethod
    def from_tool_and_meta(
        cls,
        tool: "Tool",
        meta: ToolMeta,
        source_type: str = "builtin",
        source_name: str = "",
    ) -> "ToolDocument":
        return cls(
            name=tool.name,
            description=tool.description,
            risk=meta.risk,
            always_on=meta.always_on,
            search_hint=meta.search_hint,
            source_type=source_type,
            source_name=source_name,
        )


# ── ToolRegistry ──────────────────────────────────────────────────────────────


class ToolRegistry:
    """管理所有可用工具"""

    def __init__(self, backend: SearchBackend | None = None) -> None:
        self._tools: dict[str, Tool] = {}
        self._metadata: dict[str, ToolMeta] = {}
        self._documents: dict[str, ToolDocument] = {}
        self._context_var: ContextVar[dict[str, str]] = ContextVar(
            "tool_registry_context",
            default={},
        )
        self._backend: SearchBackend = backend or KeywordSearchBackend()

    def set_context(self, **kwargs: str) -> None:
        """设置当前会话上下文（channel、chat_id 等），供工具按需读取。"""
        next_context = dict(self._context_var.get())
        next_context.update(kwargs)
        self._context_var.set(next_context)

    def get_context(self) -> dict[str, str]:
        return dict(self._context_var.get())

    def register(
        self,
        tool: Tool,
        *,
        risk: str = "read-only",
        always_on: bool = False,
        search_hint: str | None = None,
        source_type: str = "builtin",
        source_name: str = "",
        external_allowed: bool = False,
        external_limit: ExternalArgumentLimit | None = None,
    ) -> None:
        """注册工具。

        external_allowed: 声明外部上下文（群聊、陌生私聊）中非用户本人发起的回合
        也可使用此工具；未声明的工具在这类回合里不可用。MCP 动态工具不允许声明。
        external_limit: 外部可用工具在这类回合里只接受的参数取值；必须同时声明
        ``external_allowed``。
        """
        if external_allowed and source_type == "mcp":
            raise ValueError(f"MCP 工具不能声明外部上下文可用: {tool.name}")
        if external_limit is not None and not external_allowed:
            raise ValueError(f"参数限制只能用于外部上下文可用的工具: {tool.name}")
        self._tools[tool.name] = tool
        meta = ToolMeta(
            risk=risk,
            always_on=always_on,
            search_hint=search_hint,
            external_allowed=external_allowed,
            external_limit=external_limit,
        )
        self._metadata[tool.name] = meta
        doc = ToolDocument.from_tool_and_meta(
            tool, meta, source_type=source_type, source_name=source_name
        )
        self._documents[tool.name] = doc
        self._backend.add(doc)
        logger.debug(f"注册工具: {tool.name}")

    def unregister(self, name: str) -> None:
        _ = self._tools.pop(name, None)
        _ = self._metadata.pop(name, None)
        _ = self._documents.pop(name, None)
        self._backend.remove(name)
        logger.debug(f"注销工具: {name}")

    def has_tool(self, name: str) -> bool:
        return name in self._tools

    def get_tool(self, name: str) -> "Tool | None":
        return self._tools.get(name)

    def get_registered_names(self) -> set[str]:
        """返回当前已注册工具名集合。"""
        return set(self._tools.keys())

    def get_schemas(
        self,
        names: AbstractSet[str] | Iterable[str] | None = None,
        *,
        external_only: bool = False,
    ) -> list[dict[str, Any]]:
        """返回 OpenAI function calling 格式的工具定义列表。

        names 为 None 时返回全量；传 set 时按注册顺序过滤；传 list/tuple 时按调用方顺序返回。
        external_only: 外部上下文受限回合，带参数限制的工具按限制收窄 schema；
        只改写 schema，不负责过滤工具名（见 ``turn_tool_names``）。
        """
        if names is None:
            tools = list(self._tools.values())
        elif not isinstance(names, AbstractSet):
            tools = [
                tool for name in names if (tool := self._tools.get(name)) is not None
            ]
        else:
            tools = [t for name, t in self._tools.items() if name in names]
        return [self._model_schema(tool, external_only) for tool in tools]

    def _model_schema(self, tool: Tool, external_only: bool) -> dict[str, Any]:
        schema = _with_progress_description(tool.to_schema(), tool)
        limit = self._metadata[tool.name].external_limit
        if external_only and limit is not None:
            limit.restrict_schema(schema)
        return schema

    def get_registered_order(self, names: AbstractSet[str] | None = None) -> list[str]:
        if names is None:
            return list(self._tools.keys())
        return [name for name in self._tools.keys() if name in names]

    def get_always_on_names(self) -> set[str]:
        """返回标记为 always_on 的工具名称集合。"""
        return {name for name, meta in self._metadata.items() if meta.always_on}

    def is_external_allowed(self, name: str) -> bool:
        """``name`` 是否已注册且声明了外部上下文可用。

        每次都查当前注册表，回合中途新注册的未声明工具天然返回 False。
        """
        meta = self._metadata.get(name)
        return meta is not None and meta.external_allowed

    def external_denial(self, name: str, arguments: dict[str, Any]) -> str | None:
        """外部上下文受限回合里这次调用的拦截原因；可以执行时返回 None。

        未声明外部可用（或未注册）的工具一律拦截；带参数限制的工具按模型给出的
        参数判断。每次都查当前注册表。
        """
        meta = self._metadata.get(name)
        if meta is None or not meta.external_allowed:
            return EXTERNAL_TOOL_DENIED
        limit = meta.external_limit
        if limit is not None and not limit.allows(arguments):
            return limit.denied
        return None

    def get_documents(self) -> list[ToolDocument]:
        """返回所有已注册工具的索引文档列表。"""
        return list(self._documents.values())

    def get_deferred_names(
        self,
        visible: set[str] | None = None,
        *,
        external_only: bool = False,
    ) -> DeferredToolNames:
        """返回所有 deferred 工具名，按来源分组。

        visible: 当前 turn 已可见工具名（always_on + preloaded），从结果中排除。
        external_only: 只列出声明外部上下文可用的工具（外部上下文受限回合）。
        deferred = 全量注册工具 - always_on - meta_tools - visible
        格式: {"builtin": [...], "mcp": {"server_name": [...], ...}}
        """
        always_on = self.get_always_on_names()
        excluded = always_on | _META_TOOLS | (visible or set())
        builtin: list[str] = []
        mcp: dict[str, list[str]] = {}

        for name, doc in self._documents.items():
            if name in excluded or (
                external_only and not self.is_external_allowed(name)
            ):
                continue
            if doc.source_type == "mcp":
                mcp.setdefault(doc.source_name, []).append(name)
            else:
                builtin.append(name)

        return {
            "builtin": sorted(builtin),
            "mcp": {k: sorted(v) for k, v in sorted(mcp.items())},
        }

    async def execute(
        self,
        name: str,
        arguments: dict[str, Any],
        *,
        context: dict[str, Any] | None = None,
    ) -> str | ToolResult:
        tool = self._tools.get(name)
        if tool is None:
            return f"工具 '{name}' 不存在"
        try:
            execution_context = context if context is not None else self.get_context()
            # 将会话上下文（channel、chat_id）作为低优先级默认值合并进 kwargs，
            # 工具可按需读取，不感知此机制的工具会直接忽略多余的 key。
            merged: dict[str, Any] = {
                **execution_context,
                **arguments,
            }
            # 由上下文决定的键只取自执行上下文：模型传同名参数不能改写，
            # 上下文里没有时也不能由模型补上。
            for key in getattr(tool, "context_precedence", frozenset()):
                if key in execution_context:
                    merged[key] = execution_context[key]
                else:
                    merged.pop(key, None)
            if not _tool_defines_parameter(tool, _PROGRESS_DESCRIPTION_FIELD):
                merged.pop(_PROGRESS_DESCRIPTION_FIELD, None)
            return await tool.execute(**merged)
        except Exception as e:
            logger.error(f"工具 {name} 执行出错: {e}", exc_info=True)
            return f"工具执行出错: {e}"

    def get_schemas_as_doc_results(self, names: list[str]) -> list[dict[str, Any]]:
        """将工具名列表转为与 search() 相同格式的结果列表。

        供 select: 精确加载路径使用，why_matched 固定为"名称:精确匹配"。
        """
        results: list[dict[str, Any]] = []
        for name in names:
            doc = self._documents.get(name)
            if doc:
                results.append(
                    {
                        "name": doc.name,
                        "summary": doc.description[:120],
                        "why_matched": ["名称:精确匹配"],
                        "risk": doc.risk,
                        "always_on": doc.always_on,
                    }
                )
        return results

    def get_mcp_server_names(self) -> set[str]:
        """返回当前已注册的所有 MCP server 名称。"""
        return {
            doc.source_name
            for doc in self._documents.values()
            if doc.source_type == "mcp"
        }

    def get_tool_names_by_source(self, source_type: str, source_name: str) -> set[str]:
        """返回指定来源的所有工具名。"""
        return {
            name
            for name, doc in self._documents.items()
            if doc.source_type == source_type and doc.source_name == source_name
        }

    def search(
        self,
        query: str,
        top_k: int = 5,
        allowed_risk: list[str] | None = None,
        excluded_names: AbstractSet[str] | None = None,
        external_only: bool = False,
    ) -> list[dict[str, Any]]:
        """关键词搜索工具目录，返回匹配的工具信息列表。

        excluded_names: 调用方（当前 turn）传入的排除集合，通常为已可见工具名。
        external_only: 只在声明外部上下文可用的工具里搜索。
        meta_tools 始终被排除。搜索逻辑委托给 SearchBackend。
        """
        excluded = _META_TOOLS | (excluded_names or set())
        if external_only:
            excluded |= {
                name
                for name, meta in self._metadata.items()
                if not meta.external_allowed
            }
        return cast(
            list[dict[str, Any]],
            self._backend.search(
                query=query,
                top_k=top_k,
                allowed_risk=allowed_risk,
                excluded_names=excluded,
            ),
        )
