"""外部上下文的工具准入（#489）。

外部上下文（群聊、陌生私聊）里，发送者不是已绑定用户的回合只能使用允许集合内的
工具。允许集合只有一个来源：注册时声明 ``external_allowed`` 的工具（见
``ToolRegistry.is_external_allowed``），每次都查当前注册表。已绑定用户本人的
消息即使在群里也不受限。

声明时还可以附带 ``ExternalArgumentLimit``，让工具在受限回合里只接受某个参数的
部分取值（#522）：工具仍然可见，发给模型的 schema 与执行拦截两层都按这条限制
收窄（见 ``ToolRegistry.external_denial``）。
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, cast

if TYPE_CHECKING:
    from conversation.context_scope import ContextView
    from core.common.message_source import MessageSource

# 受限回合调用允许集合外的工具时，回给模型的工具结果。
EXTERNAL_TOOL_DENIED = "这个工具只有你的用户能让你使用；回复时用你平时私聊里对他的称呼"


@dataclass(frozen=True)
class ExternalArgumentLimit:
    """受限回合里，声明外部可用的工具只接受 ``argument`` 取 ``values`` 之一。

    denied: 调用参数不满足限制时回给模型的工具结果。
    note: 受限回合发给模型的工具描述末尾追加的说明。
    """

    argument: str
    values: frozenset[str]
    denied: str
    note: str

    def allows(self, arguments: Mapping[str, Any]) -> bool:
        """模型给出的调用参数是否落在允许取值内。"""
        return arguments.get(self.argument) in self.values

    def restrict_schema(self, schema: dict[str, Any]) -> None:
        """就地收窄一份工具 schema 副本：该参数限定为枚举，描述追加说明。"""
        function = cast(dict[str, Any], schema["function"])
        function["description"] = f"{function['description']}{self.note}"
        properties = cast(dict[str, Any], function["parameters"]["properties"])
        properties[self.argument] = {
            **properties[self.argument],
            "enum": sorted(self.values),
        }


def external_tools_restricted(
    context_view: "ContextView | None", source: "MessageSource"
) -> bool:
    """本回合是否只能使用外部上下文允许的工具。

    条件是回合落在外部上下文、且发送者不是已绑定用户。没有上下文视图的会话
    （非角色共享会话）不划分上下文，不受限。
    """
    return (
        context_view is not None
        and context_view.is_external
        and not source.sender_is_user
    )
