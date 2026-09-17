"""Fetch a role's post-reply mood/thought without ever blocking delivery.

The formal reply's content is plain dialogue text: no JSON envelope, no
format-correction retry (removed by #303 - unescaped quotes, newlines, and
parenthetical asides used to break the old `{content, mood, thought}` JSON
contract and cost the whole turn). Mood and thought are asked for afterward,
in one separate follow-up call that reuses the reply's own message prefix
plus the content just produced, so the model reflects on "how it felt having
just said this" rather than deciding mood before speaking. See
`fetch_role_mood` for why that call still carries the full turn budget.
"""

from __future__ import annotations

import json
import logging

from agent.provider import LLMProvider, LLMResponse, is_truncated_finish_reason
from core.common.llm_output_log import summarize_llm_output_for_log
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

    A `max_tokens` cutoff is logged distinctly (issue #304): an empty
    `content` from truncation and an empty `content` from a genuinely
    malformed reply both used to surface as the same `Expecting value: line
    1 column 1` `json.loads` error, which is exactly what misdirected the
    2026-09-17 qqbot dropped-message investigation. This is a logging-only
    change, not a new failure path: truncation is logged and the JSON parse
    is still attempted afterward exactly as before, so a `finish_reason ==
    "length"` response whose `content` happens to be complete, valid JSON
    (the API cut off only trailing whitespace/tokens the model didn't need)
    still parses and returns a fresh mood, same as pre-#304. Only a response
    that is *both* truncated *and* fails to parse degrades to None - same
    as any other malformed-JSON failure, just with the finish_reason logged
    alongside the raw (redacted, length-capped) model output so a failed
    round isn't unrecoverable after the fact.
    """
    mood_messages = [
        *messages,
        {"role": "assistant", "content": content},
        {"role": "user", "content": role_mood_prompt(moods)},
    ]
    response: LLMResponse | None = None
    try:
        response = await provider.chat(
            messages=mood_messages,
            tools=[],
            model=model,
            max_tokens=max_tokens,
            disable_thinking=True,
            response_format={"type": "json_object"},
        )
        if is_truncated_finish_reason(response.finish_reason):
            # Report truncation on its own terms so a downstream parse
            # failure (if any) doesn't read as an unexplained format
            # defect - but still attempt the parse: a max_tokens cutoff can
            # land after a complete, valid JSON object (the API trimmed
            # only trailing filler), and that case must still succeed with
            # a fresh mood exactly as it would have before this log was
            # added.
            logger.warning(
                "角色心情获取响应被截断（finish_reason=%s），model=%s raw=%s — "
                "仍会尝试解析",
                response.finish_reason,
                model,
                summarize_llm_output_for_log(response.content),
            )
        payload = json.loads(response.content or "")
        if not isinstance(payload, dict):
            raise ValueError("心情响应不是 JSON 对象")
        # Reuse the shared validator; our own `content` always wins over
        # anything the model echoed back under that key.
        return validate_role_reply({**payload, "content": content}, moods)
    except Exception as exc:
        logger.warning(
            "角色心情获取失败，本轮维持上一轮心情: %s model=%s finish_reason=%s raw=%s",
            exc,
            model,
            response.finish_reason if response is not None else None,
            summarize_llm_output_for_log(
                response.content if response is not None else None
            ),
            exc_info=True,
        )
        return None


__all__ = ["fetch_role_mood"]
