import json
from collections.abc import Set as AbstractSet
from typing import TYPE_CHECKING, Any

from agent.tools.base import Tool
from agent.tools.external_access import EXTERNAL_TOOL_DENIED
from agent.tools.registry import _META_TOOLS

if TYPE_CHECKING:
    from agent.tools.registry import ToolRegistry


# 回合经执行上下文传给 tool_search 的两个键（见 ``tool_search_call_context``）。
VISIBLE_TOOL_NAMES_KEY = "visible_tool_names"
EXTERNAL_TOOLS_ONLY_KEY = "external_tools_only"


def tool_search_call_context(
    *, visible_names: AbstractSet[str] | None, external_only: bool
) -> dict[str, Any]:
    """一次 tool_search 调用的执行上下文补充项，由回合合并进执行上下文。

    visible_names: 本回合已可见（或已禁用）的工具名，搜索与 select: 不再返回；
    None 表示不排除。external_only: 本次调用来自外部上下文受限回合，只能搜索、
    解锁声明外部可用的工具。两项都按调用传递，并且经 ``context_precedence``
    只取自执行上下文，模型不能传入或改写。
    """
    context: dict[str, Any] = {EXTERNAL_TOOLS_ONLY_KEY: external_only}
    if visible_names is not None:
        context[VISIBLE_TOOL_NAMES_KEY] = frozenset(visible_names)
    return context


class ToolSearchTool(Tool):
    """在工具目录中搜索可用工具，帮助模型发现并解锁需要的工具。

    调用此工具后，匹配到的工具将在本轮对话中解锁，可直接调用。
    """

    context_precedence = frozenset({VISIBLE_TOOL_NAMES_KEY, EXTERNAL_TOOLS_ONLY_KEY})

    def __init__(self, registry: "ToolRegistry") -> None:
        self._registry = registry

    @property
    def name(self) -> str:
        return "tool_search"

    @property
    def description(self) -> str:
        return (
            "在工具目录中搜索可用工具。搜索结果中的工具将立即解锁，之后可直接调用。\n\n"
            "调用时机：\n"
            "- 需要某类功能，但不知道工具名称 → 必须调用\n"
            "- 知道工具名且已可见 → 直接调用，不要先搜索\n"
            "- 知道工具名但不可见 → 用 select: 前缀精确加载（见下）\n"
            "- 收到'工具不存在'错误 → 必须调用，用错误中的建议关键词搜索\n"
            "- 纯对话/推理，不涉及工具能力 → 不调用\n\n"
            "查询形式：\n"
            '- "select:工具名" → 精确加载已知工具，支持逗号分隔多个："select:A,B,C"\n'
            '- "关键词" → 模糊搜索，例如："定时提醒"、"RSS订阅管理"、"Fitbit健康数据"\n\n'
            "正确流程：tool_search(query) → 从结果中选择工具 → 立即调用（不需二次搜索）"
        )

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": (
                        "搜索查询。两种形式：\n"
                        '1. "select:工具名" 精确加载（支持逗号分隔多个）\n'
                        '2. 关键词描述功能，例如："定时任务"、"文件读取"、"订阅管理"'
                    ),
                },
                "top_k": {
                    "type": "integer",
                    "description": "关键词搜索时返回的最大工具数量，默认 5，最大 10",
                    "default": 5,
                },
                "allowed_risk": {
                    "type": "array",
                    "items": {
                        "type": "string",
                        "enum": ["read-only", "write", "external-side-effect"],
                    },
                    "description": "允许的风险等级，不填则不过滤。read-only=只读，write=写操作，external-side-effect=外部副作用",
                },
            },
            "required": ["query"],
        }

    async def execute(
        self,
        query: str,
        top_k: int = 5,
        allowed_risk: list[str] | None = None,
        visible_tool_names: AbstractSet[str] | None = None,
        external_tools_only: bool = False,
        **_: Any,
    ) -> str:

        query = (query or "").strip()
        if not query:
            return json.dumps(
                {
                    "matched": [],
                    "unlocked": [],
                    "already_loaded": [],
                    "tip": "query 不能为空，请描述你需要的功能",
                },
                ensure_ascii=False,
            )

        # ── select: 精确加载路径 ──────────────────────────────────────────
        if query.lower().startswith("select:"):
            return self._handle_select(
                query[7:],
                allowed_risk=allowed_risk,
                excluded_names=visible_tool_names,
                external_only=external_tools_only,
            )

        # ── 关键词搜索路径 ────────────────────────────────────────────────
        top_k = min(max(1, int(top_k)), 10)
        results = self._registry.search(
            query=query,
            top_k=top_k,
            allowed_risk=allowed_risk,
            excluded_names=visible_tool_names,
            external_only=external_tools_only,
        )
        if not results:
            return json.dumps(
                {
                    "matched": [],
                    "unlocked": [],
                    "already_loaded": [],
                    "tip": "没有找到匹配工具，请换个关键词重试",
                },
                ensure_ascii=False,
            )
        unlocked = [
            item["name"]
            for item in results
            if isinstance(item.get("name"), str) and item["name"]
        ]
        return json.dumps(
            {
                "matched": results,
                "unlocked": unlocked,
                "already_loaded": [],
                "next_action": (
                    "unlocked 中的工具 schema 已加载。下一步直接调用需要的工具，"
                    "不要再次 tool_search。"
                ),
            },
            ensure_ascii=False,
            indent=2,
        )

    def _handle_select(
        self,
        names_str: str,
        *,
        allowed_risk: list[str] | None = None,
        excluded_names: AbstractSet[str] | None = None,
        external_only: bool = False,
    ) -> str:
        """处理 select:A,B,C 精确加载路径。

        与 search() 使用相同的过滤语义：
        - external_only 时，未声明外部可用的工具不加载，回复受限提示
        - excluded_names 中的工具已可见，无需加载（返回 tip 提示直接调用）
        - allowed_risk 不为空时，风险等级不符的工具不返回
        """
        requested = [n.strip() for n in names_str.split(",") if n.strip()]
        if not requested:
            return json.dumps(
                {
                    "matched": [],
                    "unlocked": [],
                    "already_loaded": [],
                    "tip": "select: 后面需要提供工具名",
                },
                ensure_ascii=False,
            )

        excluded = _META_TOOLS | (set(excluded_names) if excluded_names else set())
        risk_filter = set(allowed_risk) if allowed_risk else None

        already_loaded: list[str] = []
        found: list[str] = []
        missing: list[str] = []
        risk_blocked: list[str] = []
        restricted: list[str] = []

        for name in requested:
            if external_only and not self._registry.is_external_allowed(name):
                restricted.append(name)
            elif name in excluded:
                already_loaded.append(name)
            elif not self._registry.has_tool(name):
                missing.append(name)
            else:
                doc = self._registry._documents.get(name)
                if risk_filter and doc and doc.risk not in risk_filter:
                    risk_blocked.append(name)
                else:
                    found.append(name)

        matched = self._registry.get_schemas_as_doc_results(found)
        result: dict[str, Any] = {
            "matched": matched,
            "unlocked": found,
            "already_loaded": already_loaded,
        }
        if found:
            result["next_action"] = (
                "unlocked 中的工具 schema 已加载。下一步直接调用需要的工具，"
                "不要再次 tool_search。"
            )

        tip_parts: list[str] = []
        if already_loaded:
            tip_parts.append(f"已加载可直接调用: {', '.join(already_loaded)}")
        if missing:
            tip_parts.append(
                f"未找到工具: {', '.join(missing)}，请用关键词搜索确认正确名称"
            )
        if risk_blocked:
            tip_parts.append(
                f"风险等级不符（allowed_risk={allowed_risk}）: {', '.join(risk_blocked)}"
            )
        if restricted:
            tip_parts.append(f"{', '.join(restricted)}: {EXTERNAL_TOOL_DENIED}")
        if tip_parts:
            result["tip"] = "; ".join(tip_parts)

        return json.dumps(result, ensure_ascii=False, indent=2)
