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

    `max_tokens` is deliberately the caller's full turn budget, not a small
    cap of its own, even though the output is one short `{mood, thought}`
    object: in a role-backed session, `RoleAwareProvider.chat` overrides
    `disable_thinking` to False no matter what this call passes, so thinking
    stays on (it owns reasoning effort per role config, not per call - see
    `core/roles/model_runtime.py`), and this call still burns through a full
    reasoning chain before answering. A small cap here does not shorten that
    chain; it just truncates it mid-thought and leaves `content` empty,
    turning what should be a rare timeout/malformed-JSON degrade into the
    common case (measured ~2/3 of calls at a 300-token cap). `max_tokens` is
    an upper bound, not a reservation, so billing is unaffected by leaving it
    generous.

    Any failure - transport error, timeout, malformed JSON, mood outside the
    catalog, malformed thought - returns None. Callers must degrade to last
    turn's mood and still deliver `content`; this call must never fail the
    turn it belongs to. The broad `except Exception` here is deliberate, not
    an oversight: the issue's hard requirement is that this follow-up call
    must never be able to drag down the turn it belongs to, and narrowing to
    a specific exception family would risk exactly the kind of unhandled
    failure this contract exists to avoid. `exc_info=True` keeps genuine code
    defects (TypeError, AttributeError, ...) visible in logs with a
    traceback instead of silently reading as "mood call failed, degraded".
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
        logger.warning("角色心情获取失败，本轮维持上一轮心情: %s", exc, exc_info=True)
        return None


__all__ = ["fetch_role_mood"]
