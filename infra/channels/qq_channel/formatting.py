from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

CHANNEL = "qq"
GROUP_PREFIX = "gqq:"
TRACE_THINKING_LIMIT = 500
TRACE_TOOL_RESULT_LIMIT = 120
TRACE_DEFAULT_ACTOR = "Akashic"


@dataclass
class _QQTraceLine:
    tool_name: str
    status: str = "started"
    intent: str = ""
    target: str = ""
    result_preview: str = ""


@dataclass
class _QQTraceState:
    user_message: str = ""
    tool_lines: list[_QQTraceLine] = field(default_factory=list)


def session_key_for_chat(chat_id: str) -> str:
    return f"{CHANNEL}:{chat_id}"


def truncate_trace_text(text: str, limit: int) -> str:
    raw = str(text or "").strip()
    if len(raw) <= limit:
        return raw
    omitted = len(raw) - limit
    head = max(0, limit // 2)
    tail = max(0, limit - head)
    return f"{raw[:head]} ...[{omitted} chars omitted]... {raw[-tail:]}"


def format_tool_intent(arguments: dict[str, Any]) -> str:
    if not isinstance(arguments, dict):
        return ""
    for key in ("description", "query", "summary", "task", "action"):
        value = arguments.get(key)
        if isinstance(value, str) and value.strip():
            return truncate_trace_text(value, 80)
    return ""


def format_tool_target(arguments: dict[str, Any]) -> str:
    if not isinstance(arguments, dict):
        return ""
    if isinstance(arguments.get("path"), str) and arguments.get("path", "").strip():
        return truncate_trace_text(str(arguments["path"]).strip(), 60)
    if (
        isinstance(arguments.get("file_path"), str)
        and arguments.get("file_path", "").strip()
    ):
        return truncate_trace_text(str(arguments["file_path"]).strip(), 60)
    for key in (
        "cmd",
        "command",
        "query",
        "url",
        "file",
        "text",
        "content",
        "prompt",
        "name",
    ):
        value = arguments.get(key)
        if isinstance(value, str | int | float) and str(value).strip():
            return truncate_trace_text(str(value).strip(), 80)
    return ""


def format_tool_trace_lines(lines: list[_QQTraceLine]) -> str:
    if not lines:
        return "No tool calls."
    return "\n".join(
        f"{index}. {compress_tool_line(line)}"
        for index, line in enumerate(lines, start=1)
    )


def summarize_tool_result_preview(tool_name: str, preview: str) -> str:
    text = str(preview or "").strip()
    if not text:
        return ""
    name = tool_name.lower()
    if name == "fetch_messages":
        if '"matched_count"' in text or '"count"' in text:
            matched = re.search(r'"matched_count"\s*:\s*(\d+)', text)
            count = re.search(r'"count"\s*:\s*(\d+)', text)
            return (
                f"结果：命中 {matched.group(1) if matched else '?'} 条，"
                f"返回上下文 {count.group(1) if count else '?'} 条"
            )
        return "结果：已返回消息上下文"
    if name == "list_dir":
        lines = [line.strip() for line in text.splitlines() if line.strip()]
        return f"结果：列出 {len(lines)} 项" if lines else "结果：已列出目录内容"
    if name == "read_file":
        line_no = re.search(r"(\d+)→", text)
        if line_no:
            return f"结果：已读取第 {line_no.group(1)} 行附近内容"
        return "结果：已读取文件片段" if "字节" in text else "结果：已读取文件"
    if name == "shell":
        exit_code = re.search(r'"exit_code"\s*:\s*(-?\d+)', text)
        if exit_code:
            code = exit_code.group(1)
            return "结果：命令执行成功" if code == "0" else f"结果：命令退出码 {code}"
        command = re.search(r'"command"\s*:\s*"([^"]+)"', text)
        if command:
            return f"结果：已执行命令 {truncate_trace_text(command.group(1), 50)}"
        if "（无输出）" in text or "(无输出)" in text:
            return "结果：命令已执行（无输出）"
        return "结果：命令已执行"
    if name == "list_schedules":
        matched = re.search(r"(\d+)\s*个", text)
        return (
            f"结果：当前有 {matched.group(1)} 个提醒" if matched else "结果：已列出提醒"
        )
    if name == "cancel_schedule":
        matched = re.search(r"(\d+)\s*个", text)
        return (
            f"结果：已取消 {matched.group(1)} 个提醒" if matched else "结果：已执行取消"
        )
    if name == "schedule":
        return "结果：已创建提醒"
    return f"结果：{truncate_trace_text(text, TRACE_TOOL_RESULT_LIMIT)}"


def tool_emoji(tool_name: str) -> str:
    name = tool_name.lower()
    if name.startswith("mcp"):
        return "📡"
    if "search" in name or "fetch" in name:
        return "🔍"
    if "schedule" in name or "cancel" in name:
        return "⏰"
    if "shell" in name:
        return "⚙"
    if "file" in name or "read" in name or "write" in name:
        return "📄"
    return "🔧"


def compress_tool_line(line: _QQTraceLine) -> str:
    status = (
        "已完成"
        if line.status == "done"
        else "失败" if line.status == "error" else "进行中"
    )
    parts = [f"{tool_emoji(line.tool_name)} {line.tool_name}", status]
    if line.intent:
        parts.append(f"意图：{line.intent}")
    elif line.target:
        parts.append(f"目标：{line.target}")
    if line.result_preview:
        parts.append(line.result_preview)
    return " | ".join(parts)
