from __future__ import annotations

from dataclasses import dataclass

from agent.tool_hooks.finalize import (
    FINALIZE_SKIPPED_TOOL_CALL_MESSAGE,
    append_finalize_skipped_tool_results,
    is_finalize_denial,
)
from agent.tool_hooks.types import ToolExecutionResult


@dataclass
class _ToolCall:
    id: str
    name: str


def test_is_finalize_denial_requires_denied_status() -> None:
    """finalize 字段只在 status == "denied" 时有意义；即便某处误把它设成
    True，只要状态不是 denied，就不应该被当成收尾信号。"""
    success = ToolExecutionResult(
        status="success", output="ok", final_arguments={}, finalize=True
    )
    assert is_finalize_denial(success) is False


def test_is_finalize_denial_requires_the_finalize_flag() -> None:
    """普通 deny（没有结构化收尾意图）不能被误当成收尾——这正是 #239 之前
    靠 reason 字符串前缀嗅探所丢失的区分。"""
    plain_deny = ToolExecutionResult(
        status="denied", output="blocked", final_arguments={}
    )
    assert is_finalize_denial(plain_deny) is False


def test_append_finalize_skipped_tool_results_closes_every_remaining_call() -> None:
    """被截断批次里的每个 tool_call 都必须拿到一条对应的 tool result，
    否则严格 provider 或会话重放会卡在未解决的 tool_call_id 上。"""
    messages: list[dict[str, object]] = []

    append_finalize_skipped_tool_results(
        messages, [_ToolCall(id="a", name="read"), _ToolCall(id="b", name="write")]
    )

    assert [item["tool_call_id"] for item in messages] == ["a", "b"]
    assert {item["role"] for item in messages} == {"tool"}
    assert all(
        item["content"] == FINALIZE_SKIPPED_TOOL_CALL_MESSAGE for item in messages
    )


def test_append_finalize_skipped_tool_results_is_a_noop_for_an_empty_batch() -> None:
    """收尾发生在批次最后一个调用上时没有可跳过的成员，不应凭空造消息。"""
    messages: list[dict[str, object]] = []

    append_finalize_skipped_tool_results(messages, [])

    assert messages == []
