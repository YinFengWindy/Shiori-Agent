"""Fetch a role's post-reply mood/thought without ever blocking delivery.

The formal reply's content is plain dialogue text: no JSON envelope, no
format-correction retry (removed by #303 - unescaped quotes, newlines, and
parenthetical asides used to break the old `{content, mood, thought}` JSON
contract and cost the whole turn). Mood and thought are asked for afterward,
in one `disable_thinking` call that reuses the reply's own message prefix
plus the content just produced, so the model reflects on "how it felt having
just said this" rather than deciding mood before speaking.
"""

from __future__ import annotations

import json
import logging

from agent.provider import LLMProvider
from core.roles.reply_state import RoleReply, role_mood_prompt, validate_role_reply

logger = logging.getLogger(__name__)


async def fetch_role_mood(
    *,
    provider: LLMProvider,
    model: str,
    max_tokens: int,
    messages: list[dict],
    content: str,
    moods: tuple[str, ...],
) -> RoleReply | None:
    """Return a validated mood/thought that followed `content`, or None.

    `messages` is the exact prefix used to generate `content`; the produced
    content is appended as an assistant turn before asking the mood question,
    so thought reflects the moment right after speaking, not before.

    Any failure - transport error, timeout, malformed JSON, mood outside the
    catalog, malformed thought - returns None. Callers must degrade to last
    turn's mood and still deliver `content`; this call must never fail the
    turn it belongs to.
    """
    mood_messages = [
        *messages,
        {"role": "assistant", "content": content},
        {"role": "user", "content": role_mood_prompt(moods)},
    ]
    try:
        response = await provider.chat(
            messages=mood_messages,
            tools=[],
            model=model,
            max_tokens=max_tokens,
            disable_thinking=True,
            response_format={"type": "json_object"},
        )
        payload = json.loads(response.content or "")
        if not isinstance(payload, dict):
            raise ValueError("心情响应不是 JSON 对象")
        # Reuse the shared validator; our own `content` always wins over
        # anything the model echoed back under that key.
        return validate_role_reply({**payload, "content": content}, moods)
    except Exception as exc:
        logger.warning("角色心情获取失败，本轮维持上一轮心情: %s", exc)
        return None


__all__ = ["fetch_role_mood"]
