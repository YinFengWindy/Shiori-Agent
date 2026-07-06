from __future__ import annotations

import json
from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from agent.provider import LLMProvider


@dataclass(frozen=True)
class MoodResolutionInput:
    reply_text: str
    available_moods: tuple[str, ...]
    default_mood: str


async def resolve_role_mood(
    provider: "LLMProvider",
    *,
    model: str,
    max_tokens: int,
    reply_text: str,
    available_moods: list[str],
    default_mood: str,
) -> str | None:
    normalized_reply = reply_text.strip()
    normalized_moods = [mood.strip() for mood in available_moods if mood.strip()]
    normalized_default = default_mood.strip()
    if not normalized_reply or not normalized_moods:
        return None
    if normalized_default not in normalized_moods:
        normalized_default = normalized_moods[0]

    response = await provider.chat(
        messages=[
            {
                "role": "user",
                "content": (
                    "你是一个情绪分类器。"
                    "你只能从给定候选里选择一个 mood，绝对不能输出候选之外的词。"
                    "请只输出 JSON，不要输出解释。\n\n"
                    f"reply_text:\n{normalized_reply}\n\n"
                    f"available_moods: {json.dumps(normalized_moods, ensure_ascii=False)}\n"
                    f"default_mood: {normalized_default}\n\n"
                    '输出格式固定为：{"mood":"候选中的一个"}'
                ),
            },
        ],
        tools=[],
        model=model,
        max_tokens=min(120, max_tokens),
        tool_choice="none",
        disable_thinking=True,
    )
    payload = _parse_mood_payload(response.content or "")
    if not payload:
        return normalized_default
    resolved_mood = str(payload.get("mood") or "").strip()
    if resolved_mood not in normalized_moods:
        return normalized_default
    return resolved_mood


def _parse_mood_payload(raw_text: str) -> dict[str, object] | None:
    stripped = raw_text.strip()
    if not stripped:
        return None
    start = stripped.find("{")
    end = stripped.rfind("}")
    if start < 0 or end < start:
        return None
    try:
        payload = json.loads(stripped[start:end + 1])
    except json.JSONDecodeError:
        return None
    return payload if isinstance(payload, dict) else None
