from __future__ import annotations


DESKTOP_TOOL_RESULT_PREVIEW_LIMIT = 2000


def truncate_desktop_tool_result(value: object) -> str:
    """Returns a bounded tool result preview for desktop bridge payloads."""
    text = str(value or "")
    if len(text) <= DESKTOP_TOOL_RESULT_PREVIEW_LIMIT:
        return text
    return f"{text[: DESKTOP_TOOL_RESULT_PREVIEW_LIMIT - 3]}..."
