"""被动 turn 的历史读取与 prompt 辅助函数。"""

from __future__ import annotations

from collections.abc import Iterable, Sequence, Set as AbstractSet
from typing import TYPE_CHECKING, Any

from agent.prompting import is_context_frame
from agent.prompting.listening_block import HeardLine
from core.common.timekit import parse_local_iso
from conversation.context_scope import (
    belongs_to_user,
    history_filter,
    history_start,
    stored_message_source,
)

if TYPE_CHECKING:
    from agent.core.runtime_support import SessionLike
    from core.common.message_source import MessageSource
    from conversation.context_scope import ContextView
    from agent.tools.registry import ToolRegistry


# 窗口按压缩水位起算；给出 start_index 时条数上限不生效，只需为正。
_WINDOW_MESSAGES = 500


def get_window_history(
    session: "SessionLike",
    context_view: "ContextView | None" = None,
) -> list[dict]:
    """读取回合所在实际上下文的窗口水位之后的可见原文。

    外部回合只含本会话的对话；本群旁听记录不进历史，另在 context frame 里成块
    （见 ``agent.prompting.listening_block``）。
    """

    return session.get_history(
        max_messages=_WINDOW_MESSAGES,
        start_index=history_start(session, context_view),
        include=history_filter(context_view),
    )


def get_window_tool_names(
    session: "SessionLike",
    context_view: "ContextView | None" = None,
) -> list[str]:
    """读取与 get_window_history 同一窗口内用过或解锁过的工具名。"""

    return session.get_history_tool_names(
        max_messages=_WINDOW_MESSAGES,
        start_index=history_start(session, context_view),
        include=history_filter(context_view),
    )


def get_window_preloaded_tools(
    session: SessionLike,
    context_view: ContextView | None,
    tools: ToolRegistry,
) -> list[str]:
    """Resolve existing deferred tools from the current raw window in stable order."""
    always_on = tools.get_always_on_names()
    return [
        name
        for name in get_window_tool_names(session, context_view)
        if name not in always_on and tools.has_tool(name)
    ]


def get_window_sources(
    session: "SessionLike",
    context_view: "ContextView | None",
    heard: Sequence[HeardLine] = (),
) -> "tuple[MessageSource, ...]":
    """与 get_window_history 同一窗口里，非用户本人消息的来源，旧的在前。

    只有外部上下文回合需要（注入成员档案，#498）；其他回合返回空。用户本人按
    ``belongs_to_user`` 共享判定排除。本回合旁听块里的消息 ``heard`` 同样计入，与
    对话按时间合并（#539），所以只在旁听里说话或被 @ 的成员也有速记。
    """
    if context_view is None or not context_view.is_external:
        return ()
    spoken = [
        message
        for message in session.history_window(
            _WINDOW_MESSAGES,
            start_index=history_start(session, context_view),
            include=context_view.includes,
        )
        if message.get("role") == "user"
        and not belongs_to_user(message, context_view.user_threads)
    ]
    if not heard:
        return tuple(stored_message_source(message) for message in spoken)
    timeline = [
        *(
            (parse_local_iso(str(message["timestamp"])), stored_message_source(message))
            for message in spoken
        ),
        *((line.at, line.source) for line in heard if not line.source.sender_is_user),
    ]
    timeline.sort(key=lambda item: item[0])
    return tuple(source for _, source in timeline)


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
    声明外部上下文可用的工具，逐个查当前注册表。
    """
    if names is None:
        if not disabled and not external_restricted:
            return None
        names = tools.get_registered_order()
    return [
        name
        for name in names
        if name not in disabled
        and (not external_restricted or tools.is_external_allowed(name))
    ]


def build_turn_injection_prompt(
    *,
    tools: "ToolRegistry",
    tool_search_enabled: bool,
    visible_names: set[str] | None,
    external_only: bool = False,
) -> str:
    """构造当前 turn 的延迟工具提示。

    ``external_only`` 为真时目录只列声明外部上下文可用的工具（受限回合）。
    """

    if not tool_search_enabled:
        return ""
    return build_deferred_tools_hint(
        tools, visible=visible_names, external_only=external_only
    )


def build_deferred_tools_hint(
    tools: "ToolRegistry",
    visible: set[str] | None = None,
    external_only: bool = False,
) -> str:
    """将尚未加载 schema 的工具目录渲染为提示文本。"""

    deferred = tools.get_deferred_names(visible=visible, external_only=external_only)
    builtin = deferred["builtin"]
    mcp = deferred["mcp"]

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
