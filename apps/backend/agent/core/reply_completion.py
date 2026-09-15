"""One format correction inside the existing role turn, without tool replay."""

from __future__ import annotations

import json
import logging

from agent.core.passive_support import estimate_messages_tokens
from agent.core.reply_stream import RoleReplyStream
from agent.provider import (
    ContentSafetyError,
    ContextLengthError,
    LLMProvider,
    LLMResponse,
)
from core.roles.reply_state import InvalidRoleReply, parse_role_reply, role_reply_prompt

logger = logging.getLogger(__name__)


async def complete_role_reply(
    response: LLMResponse,
    *,
    provider: LLMProvider,
    model: str,
    max_tokens: int,
    messages: list[dict],
    moods: tuple[str, ...],
    stream: RoleReplyStream,
    input_token_threshold: int,
) -> tuple[LLMResponse, LLMResponse | None]:
    """Validate formal output or correct it once, retaining any delivered prefix."""
    try:
        reply = parse_role_reply(response.content or "", moods)
        await stream.finish(reply.content)
        return response, None
    except InvalidRoleReply as exc:
        logger.warning("角色正式回复格式无效，尝试一次纠正: %s", exc)
        instruction = (
            f"上一份正式回复格式不正确：{exc}。只纠正最终回复，不要重新调用工具。\n"
            + role_reply_prompt(moods)
        )
    if stream.emitted:
        instruction += (
            "\ncontent 必须原样保留以下已展示前缀，可以续写但不能改写："
            + json.dumps(stream.emitted, ensure_ascii=False)
        )
    correction_messages = [
        *messages,
        {"role": "assistant", "content": response.content or ""},
        {"role": "user", "content": instruction},
    ]
    if (
        input_token_threshold > 0
        and estimate_messages_tokens(correction_messages) >= input_token_threshold
    ):
        # This is not ContextLengthError: retrying the outer turn would replay tools.
        raise InvalidRoleReply("格式纠正超出当前回合输入预算，已停止")
    stream.begin_attempt()
    try:
        corrected = await provider.chat(
            messages=correction_messages,
            tools=[],
            model=model,
            max_tokens=max_tokens,
            response_format={"type": "json_object"},
            on_content_delta=stream.push,
        )
    except (ContextLengthError, ContentSafetyError) as exc:
        # A rejected correction must not trigger the outer context retry/tool loop.
        raise InvalidRoleReply("角色回复格式纠正被模型拒绝，已停止当前回合") from exc
    if corrected.tool_calls:
        raise InvalidRoleReply("格式纠正不允许再次调用工具")
    reply = parse_role_reply(corrected.content or "", moods)
    await stream.finish(reply.content)
    return corrected, corrected
