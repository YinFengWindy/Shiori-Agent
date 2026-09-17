from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal

HookEvent = Literal["pre_tool_use", "post_tool_use", "post_tool_error"]
ToolSource = Literal["passive", "proactive", "subagent"]
ToolExecStatus = Literal["success", "denied", "error"]
HookDecision = Literal["pass", "deny"]


@dataclass
class ToolExecutionRequest:
    call_id: str
    tool_name: str
    arguments: dict[str, Any]
    source: ToolSource
    session_key: str = ""
    channel: str = ""
    chat_id: str = ""
    request_text: str = ""
    tool_batch: tuple[dict[str, Any], ...] = field(default_factory=tuple)
    tool_batch_index: int = 0


@dataclass
class HookContext:
    event: HookEvent
    request: ToolExecutionRequest
    current_arguments: dict[str, Any]
    result: Any = ""
    error: str = ""


@dataclass
class HookOutcome:
    decision: HookDecision = "pass"
    updated_input: dict[str, Any] | None = None
    extra_message: str = ""
    reason: str = ""
    # 结构化收尾意图：与 AfterStepCtx.early_stop 同一族的信号，替代过去对
    # reason 字符串前缀（如 "tool_loop_guard:"）做插件身份嗅探。只有 deny
    # 且 finalize=True 才要求宿主截断剩余批次并进入既有总结流程；普通 deny
    # （finalize 保持默认 False）继续走今天的行为，不被误当成收尾。
    finalize: bool = False


@dataclass
class HookTraceItem:
    hook_name: str
    event: HookEvent
    matched: bool
    decision: HookDecision = "pass"
    reason: str = ""
    extra_message: str = ""
    finalize: bool = False


def _empty_str_list() -> list[str]:
    return []


def _empty_pre_trace() -> list[HookTraceItem]:
    return []


def _empty_post_trace() -> list[HookTraceItem]:
    return []


@dataclass
class ToolExecutionResult:
    status: ToolExecStatus
    output: Any
    final_arguments: dict[str, Any]
    extra_messages: list[str] = field(default_factory=_empty_str_list)
    pre_hook_trace: list[HookTraceItem] = field(default_factory=_empty_pre_trace)
    post_hook_trace: list[HookTraceItem] = field(default_factory=_empty_post_trace)
    # 仅在 status == "denied" 时可能为 True：由拒绝该次调用的 pre_hook 的
    # HookOutcome.finalize 透传而来，见该字段的文档。
    finalize: bool = False


# LLM 可见、非用户可见的通用收尾提示：任意 hook 触发结构化收尾意图时，
# 同一批次里被跳过的后续 tool_call 都用这条统一文案回填 tool result，
# 不再是仅描述"重复循环检测"这一种收尾原因的三份拷贝。
FINALIZE_SKIPPED_TOOL_CALL_MESSAGE = "工具调用已跳过：本轮工具调用已提前收尾。"


def is_finalize_denial(exec_result: "ToolExecutionResult") -> bool:
    """True when a denied tool execution carries a structured finalize intent.

    主推理循环与子 Agent 用这个共享判定替代过去按插件名/ reason 字符串前缀
    做的嗅探（见 HookOutcome.finalize 的文档）：任何 hook、任何插件身份，
    只要在 deny 时设置了 finalize=True，都会被当作"截断并收尾"；没有设置
    该字段的普通 deny 保持原行为，不被误判。
    """
    return exec_result.status == "denied" and bool(exec_result.finalize)
