"""Provider JSONL 流的增量解码与统一事件映射。"""

from __future__ import annotations

import json
from collections.abc import Iterable, Mapping
from typing import Any

from .base import AdapterError, AdapterEvent


def decode_json_line(line: bytes) -> Mapping[str, Any] | None:
    """以 UTF-8 解码单行 JSON，空行返回 None。"""
    try:
        text = line.decode("utf-8", errors="strict").strip()
    except UnicodeDecodeError as exc:
        raise AdapterError(
            "unsupported_capability",
            "CLI 输出了非 UTF-8 JSONL 事件",
        ) from exc
    if not text:
        return None
    try:
        value = json.loads(text)
    except json.JSONDecodeError as exc:
        raise AdapterError(
            "unsupported_capability",
            f"CLI 输出了无法解析的 JSONL 事件: {text[:200]}",
        ) from exc
    if not isinstance(value, dict):
        raise AdapterError(
            "unsupported_capability",
            "CLI JSONL 顶层事件必须是对象",
        )
    return value


def _content_blocks(message: object) -> Iterable[Mapping[str, Any]]:
    if not isinstance(message, dict):
        return ()
    content = message.get("content", ())
    if not isinstance(content, list):
        return ()
    return (block for block in content if isinstance(block, dict))


def parse_codex_event(raw: Mapping[str, Any]) -> list[AdapterEvent]:
    """将 Codex exec JSONL 事件转换为统一事件。"""
    event_type = raw.get("type")
    if event_type == "thread.started":
        return [
            AdapterEvent(
                "process_started",
                {"session_id": raw.get("thread_id")},
                raw,
            )
        ]
    if event_type in {"error", "turn.failed"}:
        message = raw.get("message") or raw.get("error") or "Codex 运行失败"
        return [AdapterEvent("adapter_error", {"message": str(message)}, raw)]
    if event_type not in {"item.started", "item.updated", "item.completed"}:
        return []
    item = raw.get("item")
    if not isinstance(item, dict):
        return []
    item_type = item.get("type")
    if item_type in {"agent_message", "reasoning"}:
        text = item.get("text")
        if isinstance(text, str) and text:
            return [AdapterEvent("assistant_delta", {"text": text}, raw)]
        return []
    if item_type in {"command_execution", "mcp_tool_call", "tool_call"}:
        payload = {
            "id": item.get("id"),
            "name": item.get("name") or item_type,
            "command": item.get("command"),
            "status": item.get("status"),
        }
        unified_type = (
            "tool_finished" if event_type == "item.completed" else "tool_started"
        )
        return [AdapterEvent(unified_type, payload, raw)]
    if item_type in {"file_change", "artifact"} and event_type == "item.completed":
        return [AdapterEvent("artifact_created", dict(item), raw)]
    if item_type == "approval_request":
        return [AdapterEvent("approval_requested", dict(item), raw)]
    return []


def parse_claude_event(raw: Mapping[str, Any]) -> list[AdapterEvent]:
    """将 Claude stream-json 事件转换为统一事件。"""
    event_type = raw.get("type")
    if event_type == "system" and raw.get("subtype") == "init":
        return [
            AdapterEvent(
                "process_started",
                {"session_id": raw.get("session_id"), "model": raw.get("model")},
                raw,
            )
        ]
    if event_type == "stream_event":
        nested = raw.get("event")
        if not isinstance(nested, dict):
            return []
        if nested.get("type") == "content_block_delta":
            delta = nested.get("delta")
            if isinstance(delta, dict) and delta.get("type") == "text_delta":
                text = delta.get("text")
                if isinstance(text, str) and text:
                    return [AdapterEvent("assistant_delta", {"text": text}, raw)]
        if nested.get("type") == "content_block_start":
            block = nested.get("content_block")
            if isinstance(block, dict) and block.get("type") == "tool_use":
                return [
                    AdapterEvent(
                        "tool_started",
                        {"id": block.get("id"), "name": block.get("name")},
                        raw,
                    )
                ]
        return []
    if event_type == "assistant":
        events: list[AdapterEvent] = []
        for block in _content_blocks(raw.get("message")):
            if block.get("type") == "text" and isinstance(block.get("text"), str):
                events.append(
                    AdapterEvent("assistant_delta", {"text": block["text"]}, raw)
                )
            elif block.get("type") == "tool_use":
                events.append(
                    AdapterEvent(
                        "tool_started",
                        {"id": block.get("id"), "name": block.get("name")},
                        raw,
                    )
                )
        return events
    if event_type == "user":
        events = []
        for block in _content_blocks(raw.get("message")):
            if block.get("type") == "tool_result":
                events.append(
                    AdapterEvent(
                        "tool_finished",
                        {
                            "id": block.get("tool_use_id"),
                            "is_error": block.get("is_error", False),
                        },
                        raw,
                    )
                )
        return events
    if event_type == "result":
        if raw.get("is_error"):
            return [
                AdapterEvent(
                    "adapter_error",
                    {"message": str(raw.get("result") or raw.get("subtype"))},
                    raw,
                )
            ]
        result = raw.get("result")
        if isinstance(result, str) and result:
            return [AdapterEvent("assistant_delta", {"text": result}, raw)]
    return []
