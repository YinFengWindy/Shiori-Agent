"""结构化收尾意图的宿主侧消费逻辑（#239）。

与 ``types.py`` 分开：那里只放工具执行契约的数据形状（``HookOutcome``、
``HookTraceItem``、``ToolExecutionResult``），这里放宿主依据 ``finalize``
字段做判定和改写消息链的行为。放一起会让契约模块同时承担数据定义、判定
和消息副作用三类职责，也会逼出一个函数内 import 来回避对
``agent.tool_runtime`` 的模块级依赖。
"""

from __future__ import annotations

from collections.abc import Iterable
from typing import Any

from agent.tool_hooks.types import ToolExecutionResult
from agent.tool_runtime import append_tool_result

# LLM 可见、非用户可见的通用收尾提示：任意 hook 触发结构化收尾意图时，
# 同一批次里被跳过的后续 tool_call 都用这条统一文案回填 tool result，
# 不再是仅描述"重复循环检测"这一种收尾原因的三份拷贝。
FINALIZE_SKIPPED_TOOL_CALL_MESSAGE = "工具调用已跳过：本轮工具调用已提前收尾。"


def is_finalize_denial(exec_result: ToolExecutionResult) -> bool:
    """True when a denied tool execution carries a structured finalize intent.

    主推理循环与子 Agent 用这个共享判定替代过去按插件名/ reason 字符串前缀
    做的嗅探（见 HookOutcome.finalize 的文档）：任何 hook、任何插件身份，
    只要在 deny 时设置了 finalize=True，都会被当作"截断并收尾"；没有设置
    该字段的普通 deny 保持原行为，不被误判。
    """
    return exec_result.status == "denied" and bool(exec_result.finalize)


def append_finalize_skipped_tool_results(
    messages: list[dict[str, Any]],
    skipped_tool_calls: Iterable[Any],
) -> None:
    """Backfills a tool result for every batch member a finalize skipped.

    Every ``tool_call`` in an assistant message must get a matching ``tool``
    result message, or a strict provider / session replay chokes on an
    unresolved ``tool_call_id``. Both consumption sites of the finalize
    contract (the main-turn reasoning loop, in two branches, and
    ``SubAgent``) need to close out the remainder of a truncated batch the
    same way; this is the one place that loop lives instead of three copies
    of it drifting apart.
    """
    for skipped in skipped_tool_calls:
        append_tool_result(
            messages,
            tool_call_id=skipped.id,
            content=FINALIZE_SKIPPED_TOOL_CALL_MESSAGE,
            tool_name=skipped.name,
        )
