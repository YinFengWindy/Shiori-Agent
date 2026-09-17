from __future__ import annotations

from dataclasses import dataclass
import json
import logging
import re
from typing import Any

from core.common.llm_output_log import summarize_llm_output_for_log

logger = logging.getLogger(__name__)


@dataclass
class ResponseMetadata:
    """Formal reply fields retained separately from the displayed content."""

    raw_text: str
    mood: str | None = None
    thought: str | None = None


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
    payload = parse_response_json_payload(stripped) or find_response_json_payload(
        stripped
    )
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
    except json.JSONDecodeError as exc:
        # Shaped like a JSON object (braces at both ends) but didn't parse -
        # a genuine format failure, unlike the common case just above where
        # there is no brace-wrapped payload at all (plain dialogue since
        # #303, expected, not logged). Log the raw text so a failed round
        # is still diagnosable; no model/finish_reason here since this
        # module only ever sees the text, not the LLMResponse it came from.
        logger.warning(
            "结构化输出解析失败：疑似 JSON 对象但解析出错 err=%s raw=%s",
            exc,
            summarize_llm_output_for_log(raw_text),
        )
        return None
    return payload if isinstance(payload, dict) else None


def find_response_json_payload(raw_text: str) -> dict[str, Any] | None:
    candidate = extract_first_json_object(raw_text)
    if not candidate:
        return None
    payload = parse_response_json_payload(candidate)
    if not payload:
        return None
    if "content" not in payload and "mood" not in payload:
        return None
    return payload


def extract_first_json_object(raw_text: str) -> str | None:
    start = raw_text.find("{")
    if start < 0:
        return None
    depth = 0
    in_string = False
    escaped = False
    for index in range(start, len(raw_text)):
        char = raw_text[index]
        if in_string:
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == '"':
                in_string = False
            continue
        if char == '"':
            in_string = True
            continue
        if char == "{":
            depth += 1
            continue
        if char == "}":
            depth -= 1
            if depth == 0:
                return raw_text[start : index + 1]
    return None


def normalize_mood_value(value: object) -> str | None:
    mood = re.sub(r"\s+", " ", str(value or "").strip())
    return mood or None
