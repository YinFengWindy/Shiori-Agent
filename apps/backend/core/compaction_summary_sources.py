"""Bound summary input to stored text, attachment references and tool outcomes."""

from typing import Any
from conversation.context_scope import stored_message_source
from session.manager.helpers import truncate_tool_result
from session.manager.models import message_thread_id

_SOURCE_KEYS = (
    "id",
    "role",
    "content",
    "media",
    "tool_chain",
    "tool_calls",
    "tool_call_id",
    "name",
    "timestamp",
)


def summary_source(message: dict[str, Any]) -> dict[str, Any]:
    """Project one stored message into summary input, bounded like model history.

    Original text, attachment references and completed tool outcomes are the
    semantic source. Never stringify llm_user_content's Base64 image blocks.
    """
    source = {key: message[key] for key in _SOURCE_KEYS if key in message} | {
        "source": stored_message_source(message).to_metadata(),
        "thread_id": message_thread_id(message),
    }
    if source.get("tool_chain"):
        source["tool_chain"] = [
            group
            | {
                "calls": [
                    call
                    | (
                        {"result": truncate_tool_result(call["result"])}
                        if "result" in call
                        else {}
                    )
                    for call in group.get("calls") or []
                ]
            }
            for group in source["tool_chain"]
        ]
    return source


def shrink_summary_source(value: Any, limit: int) -> Any:
    """Apply the tool-result truncation rule to every text longer than ``limit``."""
    if isinstance(value, str):
        return truncate_tool_result(value, limit) if len(value) > limit else value
    if isinstance(value, dict):
        return {key: shrink_summary_source(item, limit) for key, item in value.items()}
    if isinstance(value, list):
        return [shrink_summary_source(item, limit) for item in value]
    return value
