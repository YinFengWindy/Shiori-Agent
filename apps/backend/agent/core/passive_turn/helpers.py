"""被动 turn 的历史读取与 prompt 辅助函数。"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from agent.prompting import is_context_frame

if TYPE_CHECKING:
    from agent.core.runtime_support import SessionLike
    from agent.tools.registry import ToolRegistry

def get_history_since_consolidated(
    session: "SessionLike",
    memory_window: int,
) -> list[dict]:
    """读取最近一次记忆整合之后的会话历史。"""

    try:
        return session.get_history(
            max_messages=memory_window,
            start_index=session.last_consolidated,
        )
    except TypeError:
        return session.get_history(max_messages=memory_window)


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
        messages[-1].get("content")
        if messages[-1].get("role") == "user"
        else None
    )
    if len(messages) < 2:
        return user_content, None
    frame = messages[-2]
    frame_content = frame.get("content")
    if isinstance(frame_content, str) and is_context_frame(frame_content):
        return user_content, frame_content
    return user_content, None


def build_turn_injection_prompt(
    *,
    tools: "ToolRegistry",
    tool_search_enabled: bool,
    visible_names: set[str] | None,
) -> str:
    """构造当前 turn 的延迟工具提示。"""

    if not tool_search_enabled:
        return ""
    return build_deferred_tools_hint(tools, visible=visible_names)


def build_deferred_tools_hint(
    tools: "ToolRegistry",
    visible: set[str] | None = None,
) -> str:
    """将尚未加载 schema 的工具目录渲染为提示文本。"""

    get_deferred_names = getattr(tools, "get_deferred_names", None)
    if not callable(get_deferred_names):
        return ""
    deferred_raw = get_deferred_names(visible=visible)
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
        "- 已知工具名 → tool_search(query=\"select:工具名\")，支持逗号分隔多个\n"
        "- 描述功能   → tool_search(query=\"关键词\") 搜索匹配"
    )
    return "\n".join(lines) + "\n\n"
