"""被动 turn 的历史读取与 prompt 辅助函数。"""

from __future__ import annotations

from collections.abc import Iterable, Set as AbstractSet
from typing import TYPE_CHECKING, Any, overload

from agent.prompting import is_context_frame
from conversation.context_scope import history_filter

if TYPE_CHECKING:
    from agent.core.runtime_support import SessionLike
    from conversation.context_scope import ContextView
    from agent.tools.registry import ToolRegistry


def get_history_since_consolidated(
    session: "SessionLike",
    memory_window: int,
    context_view: "ContextView | None" = None,
) -> list[dict]:
    """读取最近一次记忆整合之后、回合所在上下文可见的会话历史。"""

    return session.get_history(
        max_messages=memory_window,
        start_index=session.last_consolidated,
        include=history_filter(context_view),
    )


def get_history_tool_names_since_consolidated(
    session: "SessionLike",
    memory_window: int,
    context_view: "ContextView | None" = None,
) -> list[str]:
    """读取与 get_history_since_consolidated 同一窗口内用过或解锁过的工具名。"""

    return session.get_history_tool_names(
        max_messages=memory_window,
        start_index=session.last_consolidated,
        include=history_filter(context_view),
    )


def get_session_metadata(session: object) -> dict[str, Any]:
    """返回会话 metadata；无有效字典时返回空字典。"""

    metadata = getattr(session, "metadata", None)
    return metadata if isinstance(metadata, dict) else {}


def extract_model_facing_turn(
    messages: list[dict],
) -> tuple[object | None, str | None]:
    """提取模型实际看到的当前用户内容与上下文 frame。"""

    if not messages:
        return None, None
    user_content = (
        messages[-1].get("content") if messages[-1].get("role") == "user" else None
    )
    if len(messages) < 2:
        return user_content, None
    frame = messages[-2]
    frame_content = frame.get("content")
    if isinstance(frame_content, str) and is_context_frame(frame_content):
        return user_content, frame_content
    return user_content, None


@overload
def turn_tool_names(
    tools: "ToolRegistry",
    names: Iterable[str],
    *,
    disabled: AbstractSet[str],
    external_restricted: bool,
) -> list[str]: ...


@overload
def turn_tool_names(
    tools: "ToolRegistry",
    names: None,
    *,
    disabled: AbstractSet[str],
    external_restricted: bool,
) -> list[str] | None: ...


def turn_tool_names(
    tools: "ToolRegistry",
    names: Iterable[str] | None,
    *,
    disabled: AbstractSet[str],
    external_restricted: bool,
) -> list[str] | None:
    """本回合可以发给模型的工具名，保持 ``names`` 的顺序。

    ``names`` 为 None 表示全部已注册工具；没有任何限制时仍返回 None（全量）。
    ``disabled`` 是后台任务禁用的工具；``external_restricted`` 为真时只保留
    外部上下文允许集合内的工具，允许集合在调用时从注册表现算。
    """
    if names is None:
        if not disabled and not external_restricted:
            return None
        names = tools.get_registered_order()
    allowed = tools.get_external_allowed_names() if external_restricted else None
    return [
        name
        for name in names
        if name not in disabled and (allowed is None or name in allowed)
    ]


def build_turn_injection_prompt(
    *,
    tools: "ToolRegistry",
    tool_search_enabled: bool,
    visible_names: set[str] | None,
    allowed_names: AbstractSet[str] | None = None,
) -> str:
    """构造当前 turn 的延迟工具提示。

    ``allowed_names`` 不为 None 时目录只列其中的工具（外部上下文受限回合）。
    """

    if not tool_search_enabled:
        return ""
    return build_deferred_tools_hint(
        tools, visible=visible_names, allowed=allowed_names
    )


def build_deferred_tools_hint(
    tools: "ToolRegistry",
    visible: set[str] | None = None,
    allowed: AbstractSet[str] | None = None,
) -> str:
    """将尚未加载 schema 的工具目录渲染为提示文本。"""

    get_deferred_names = getattr(tools, "get_deferred_names", None)
    if not callable(get_deferred_names):
        return ""
    deferred_raw = get_deferred_names(visible=visible, allowed=allowed)
    if not isinstance(deferred_raw, dict):
        return ""
    builtin_raw = deferred_raw.get("builtin", [])
    mcp_raw = deferred_raw.get("mcp", {})
    builtin = [name for name in builtin_raw if isinstance(name, str)]
    mcp = {
        str(server): [name for name in names if isinstance(name, str)]
        for server, names in mcp_raw.items()
        if isinstance(server, str) and isinstance(names, list)
    }

    if not builtin and not mcp:
        return ""

    lines: list[str] = ["【未加载工具目录（知道名字但 schema 未暴露）】"]
    if builtin:
        lines.append(f"内置: {', '.join(builtin)}")
    for server, names in mcp.items():
        lines.append(f"MCP ({server}): {', '.join(names)}")

    total = len(builtin) + sum(len(v) for v in mcp.values())
    lines.append(
        f"\n共 {total} 个。加载方式：\n"
        '- 已知工具名 → tool_search(query="select:工具名")，支持逗号分隔多个\n'
        '- 描述功能   → tool_search(query="关键词") 搜索匹配'
    )
    return "\n".join(lines) + "\n\n"
