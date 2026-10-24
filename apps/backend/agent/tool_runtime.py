from __future__ import annotations

import json
from dataclasses import dataclass
from collections.abc import Iterable, Sequence
from typing import Any, cast

from shiori_sdk.tools import Tool, ToolResult, normalize_tool_result


@dataclass(frozen=True)
class PreparedToolset:
    tools: list[Tool]
    schemas: list[dict[str, Any]]
    tool_map: dict[str, Tool]


def prepare_toolset(tools: list[Tool]) -> PreparedToolset:
    return PreparedToolset(
        tools=list(tools),
        schemas=build_tool_schemas(tools),
        tool_map=build_tool_map(tools),
    )


def build_tool_schemas(tools: list[Tool]) -> list[dict[str, Any]]:
    return [
        {
            "type": "function",
            "function": {
                "name": tool.name,
                "description": tool.description,
                "parameters": tool.parameters,
            },
        }
        for tool in tools
    ]


def build_tool_map(tools: list[Tool]) -> dict[str, Tool]:
    return {tool.name: tool for tool in tools}


def tool_call_batch_snapshot(tool_calls: Sequence[Any]) -> tuple[dict[str, Any], ...]:
    batch: list[dict[str, Any]] = []
    for tool_call in tool_calls:
        raw_arguments: object = getattr(tool_call, "arguments", {})
        snapshot_args: dict[str, Any] = {}
        if isinstance(raw_arguments, dict):
            for key, value in cast("dict[Any, Any]", raw_arguments).items():
                snapshot_args[str(key)] = value
        batch.append(
            {
                "name": str(getattr(tool_call, "name", "")),
                "arguments": snapshot_args,
            }
        )
    return tuple(batch)


def format_tool_calls(tool_calls: list[Any]) -> list[dict[str, Any]]:
    return [
        {
            "id": tool_call.id,
            "type": "function",
            "function": {
                "name": tool_call.name,
                "arguments": json.dumps(
                    tool_call.arguments,
                    ensure_ascii=False,
                ),
            },
        }
        for tool_call in tool_calls
    ]


def append_assistant_tool_calls(
    messages: list[dict[str, Any]],
    *,
    content: str | None,
    tool_calls: list[Any],
    provider_fields: dict[str, Any] | None = None,
) -> None:
    message: dict[str, Any] = {
        "role": "assistant",
        "content": content,
        "tool_calls": format_tool_calls(tool_calls),
    }
    if provider_fields:
        message.update(provider_fields)
    messages.append(message)


def append_tool_result(
    messages: list[dict[str, Any]],
    *,
    tool_call_id: str,
    content: str | ToolResult,
    tool_name: str | None = None,
) -> None:
    result = normalize_tool_result(content)
    # A model may request multiple tools together. Keep their replies contiguous;
    # multimodal observations from earlier replies remain after the complete batch.
    insert_at = len(messages)
    for index in range(len(messages) - 1, -1, -1):
        if messages[index].get("role") == "assistant":
            if messages[index].get("tool_calls"):
                insert_at = next(
                    (
                        offset
                        for offset in range(index + 1, len(messages))
                        if messages[offset].get("role") != "tool"
                    ),
                    len(messages),
                )
            break
    messages.insert(
        insert_at,
        {
            "role": "tool",
            "tool_call_id": tool_call_id,
            "content": result.text or "工具执行完成。",
        },
    )
    if result.content_blocks:
        prefix = (
            f"以下是工具 {tool_name} 返回的内容，请直接查看。"
            if tool_name
            else "以下是工具返回的内容，请直接查看。"
        )
        messages.append(
            {
                "role": "user",
                "content": [{"type": "text", "text": prefix}, *result.content_blocks],
            }
        )


# LLM 可见、非用户可见的通用收尾提示：任意插件触发结构化收尾意图时，
# 同一批次里被跳过的后续 tool_call 都用这条统一文案回填 tool result。
FINALIZE_SKIPPED_TOOL_CALL_MESSAGE = "工具调用已跳过：本轮工具调用已提前收尾。"


def append_finalize_skipped_tool_results(
    messages: list[dict[str, Any]],
    skipped_tool_calls: Iterable[Any],
) -> None:
    """Backfills a tool result for every batch member a finalize skipped.

    Every ``tool_call`` in an assistant message must get a matching ``tool``
    result message, or a strict provider / session replay chokes on an
    unresolved ``tool_call_id``. The passive reasoning loop (both branches)
    and ``SubAgent`` close a truncated batch this way.
    """
    for skipped in skipped_tool_calls:
        append_tool_result(
            messages,
            tool_call_id=skipped.id,
            content=FINALIZE_SKIPPED_TOOL_CALL_MESSAGE,
            tool_name=skipped.name,
        )
