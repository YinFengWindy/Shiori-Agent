from __future__ import annotations

from dataclasses import dataclass
import json
import re
from typing import Any


@dataclass
class ResponseMetadata:
    raw_text: str
    mood: str | None = None


@dataclass
class ParsedResponse:
    clean_text: str
    metadata: ResponseMetadata


def parse_response(
    raw_text: str,
    *,
    tool_chain: list[dict[str, object]],
) -> ParsedResponse:
    clean_text, mood = extract_structured_mood(raw_text)
    return ParsedResponse(
        clean_text=clean_text,
        metadata=ResponseMetadata(raw_text=raw_text, mood=mood),
    )


def extract_structured_mood(raw_text: str) -> tuple[str, str | None]:
    stripped = raw_text.strip()
    if not stripped:
        return raw_text, None
    payload = parse_response_json_payload(stripped)
    if not payload:
        return raw_text, None
    content = str(payload.get("content") or "").strip()
    mood = normalize_mood_value(payload.get("mood"))
    if not content:
        return raw_text, mood
    return content, mood


def parse_response_json_payload(raw_text: str) -> dict[str, Any] | None:
    if not raw_text.startswith("{") or not raw_text.endswith("}"):
        return None
    try:
        payload = json.loads(raw_text)
    except json.JSONDecodeError:
        return None
    return payload if isinstance(payload, dict) else None


def normalize_mood_value(value: object) -> str | None:
    mood = re.sub(r"\s+", " ", str(value or "").strip())
    return mood or None
