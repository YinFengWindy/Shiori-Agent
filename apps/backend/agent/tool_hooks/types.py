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

    def to_dict(self) -> dict[str, Any]:
        """Serializes to the shape persisted into ``tool_chain`` calls.

        Single source of truth for that field list: callers used to spell
        out ``{"hook_name": item.hook_name, "event": item.event, ...}``
        themselves at every call site, so a new field meant hunting down and
        editing three separate literals in lockstep.
        """
        return {
            "hook_name": self.hook_name,
            "event": self.event,
            "matched": self.matched,
            "decision": self.decision,
            "reason": self.reason,
            "extra_message": self.extra_message,
            "finalize": self.finalize,
        }


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
