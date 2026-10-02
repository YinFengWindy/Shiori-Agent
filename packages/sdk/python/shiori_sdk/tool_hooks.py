"""Pre-tool inputs and decisions shared by all tool policy plugins."""

from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import Any, Literal, Protocol

HookDecision = Literal["pass", "deny"]


@dataclass
class PreToolCtx:
    """pre-tool hook 上下文 — mutable，handler 返回 dict 表示新 arguments"""

    session_key: str
    channel: str
    chat_id: str
    tool_name: str
    arguments: dict[str, Any]
    call_id: str = ""
    source: str = ""
    request_text: str = ""
    tool_batch: tuple[dict[str, Any], ...] = field(default_factory=tuple)
    tool_batch_index: int = 0


@dataclass
class HookOutcome:
    """Pass, rewrite, or deny a call; finalize explicitly requests host summarization."""

    decision: HookDecision = "pass"
    updated_input: dict[str, Any] | None = None
    extra_message: str = ""
    reason: str = ""
    # 结构化收尾意图：与 AfterStepCtx.early_stop 同一族的信号，替代过去对
    # reason 字符串前缀（如 "tool_loop_guard:"）做插件身份嗅探。只有 deny
    # 且 finalize=True 才要求宿主截断剩余批次并进入既有总结流程；普通 deny
    # （finalize 保持默认 False）继续走今天的行为，不被误当成收尾。
    finalize: bool = False


PreToolHandler = Callable[
    [PreToolCtx],
    Awaitable[HookOutcome | dict[str, object] | None]
    | HookOutcome
    | dict[str, object]
    | None,
]


class ToolHooksCapability(Protocol):
    """Register pre-tool handlers scoped to one plugin generation."""

    def add_handler(
        self,
        handler: PreToolHandler,
        *,
        tool_name_filter: str | None = None,
        handler_name: str | None = None,
    ) -> None: ...
