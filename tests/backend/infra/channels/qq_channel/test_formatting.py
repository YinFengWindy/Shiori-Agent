from __future__ import annotations

from infra.channels.qq_channel.formatting import (
    _QQTraceLine,
    format_tool_trace_lines,
    summarize_tool_result_preview,
)


def test_formatting_summarizes_shell_success_without_raw_payload() -> None:
    assert (
        summarize_tool_result_preview("shell", '{"exit_code": 0, "stdout": "large"}')
        == "结果：命令执行成功"
    )


def test_formatting_renders_trace_status_and_intent() -> None:
    rendered = format_tool_trace_lines(
        [_QQTraceLine(tool_name="search", status="done", intent="find docs")]
    )

    assert "search" in rendered
    assert "已完成" in rendered
    assert "意图：find docs" in rendered
