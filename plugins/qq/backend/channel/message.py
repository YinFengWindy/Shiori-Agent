"""Normalize NapCat's structured messages without treating literal text as CQ codes."""

from __future__ import annotations

from typing import Any


def cq_escape(value: str, *, parameter: bool = True) -> str:
    """Escape a OneBot text segment or CQ parameter exactly once."""
    escaped = value.replace("&", "&amp;").replace("[", "&#91;").replace("]", "&#93;")
    return escaped.replace(",", "&#44;") if parameter else escaped


def message_content(payload: dict[str, Any]) -> str:
    """Prefer structured segments, which preserve file IDs and download URLs."""
    message = payload.get("message")
    if isinstance(message, list):
        parts: list[str] = []
        for segment in message:
            kind, data = segment["type"], segment["data"]
            if kind == "text":
                parts.append(cq_escape(str(data.get("text") or ""), parameter=False))
            else:
                parameters = "".join(
                    f",{key}={cq_escape(str(value))}" for key, value in data.items()
                )
                parts.append(f"[CQ:{kind}{parameters}]")
        return "".join(parts)
    raw = payload.get("raw_message")
    return raw if isinstance(raw, str) else message if isinstance(message, str) else ""
