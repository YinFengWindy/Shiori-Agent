"""Local input costs, used only when provider token counts are unavailable."""

from __future__ import annotations

import math
from typing import Any


def estimate_tokens(value: Any) -> int:
    """Count text and structure conservatively, keeping images independent of URLs.

    CJK and other non-ASCII text gets two tokens per character. Image cost is a
    conservative fixed allowance (4096, or 85 for explicit low detail), not a
    tokenizer claim; a subsequent provider usage sample calibrates the request.
    """
    if isinstance(value, str):
        non_ascii = sum(ord(char) > 127 for char in value)
        return math.ceil((len(value) - non_ascii) / 3) + non_ascii * 2
    if isinstance(value, dict):
        if value.get("type") == "image_url":
            image = value.get("image_url") or {}
            return (
                85 if isinstance(image, dict) and image.get("detail") == "low" else 4096
            )
        return 2 + sum(
            estimate_tokens(str(k)) + estimate_tokens(v) + 2 for k, v in value.items()
        )
    if isinstance(value, (list, tuple)):
        return 2 + sum(estimate_tokens(item) + 2 for item in value)
    return estimate_tokens(str(value)) if value is not None else 1


def estimate_input(messages: list[dict], tools: list[dict] | None = None) -> int:
    """Estimate the complete messages and schema once, without output reservation."""
    if not messages and not tools:
        return 0
    return estimate_tokens(
        {"messages": messages, **({"tools": tools} if tools else {})}
    )
