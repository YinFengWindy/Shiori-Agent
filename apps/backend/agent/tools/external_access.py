"""外部上下文的工具准入（#489）。

外部上下文（群聊、陌生私聊）里，发送者不是已绑定用户的回合只能使用允许集合内的
工具。允许集合只有一个来源：注册时声明 ``external_allowed`` 的工具（见
``ToolRegistry.get_external_allowed_names``），每次查询现算。已绑定用户本人的
消息即使在群里也不受限。
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from conversation.context_scope import ContextView
    from core.common.message_source import MessageSource

# 受限回合调用允许集合外的工具时，回给模型的工具结果。
EXTERNAL_TOOL_DENIED = "这个工具只有你的用户能让你使用；回复时用你平时私聊里对他的称呼"


def external_tools_restricted(
    context_view: "ContextView | None", source: "MessageSource"
) -> bool:
    """本回合是否只能使用外部上下文允许的工具。

    条件是回合落在外部上下文、且发送者不是已绑定用户。没有上下文视图的会话
    （非角色共享会话）不划分上下文，不受限。
    """
    return (
        context_view is not None
        and context_view.scope == "external"
        and not source.sender_is_user
    )
