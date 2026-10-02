"""Complete ordinary and summary replies with one tools-free recovery attempt."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any, Awaitable, Callable

from agent.core.reply_output import RoleReplyOutput
from agent.provider import LLMProvider, LLMResponse
from .compaction import ensure_request_budget
from .empty_reply import EmptyReplyError, recovery_diagnostics, response_diagnostics

logger = logging.getLogger("agent.core.passive_turn")


@dataclass
class CompletedReply:
    """Final response, all billed calls, and optional persisted recovery facts."""

    response: LLMResponse
    calls: tuple[LLMResponse, ...]
    diagnostics: dict[str, Any] | None = None

    @property
    def total_tokens(self) -> int | None:
        """Include the initial empty call when accounting for summary recovery."""
        values = [
            call.total_tokens for call in self.calls if call.total_tokens is not None
        ]
        return sum(values) if values else None


async def complete_reply(
    response: LLMResponse,
    *,
    output: RoleReplyOutput,
    messages: list[dict],
    provider: LLMProvider,
    model: str,
    max_tokens: int,
    role_reply: bool,
    on_content_delta: Callable[[dict[str, str]], Awaitable[None]] | None = None,
    session: str,
    channel: str,
    iteration: int,
    allow_tool_calls: bool = False,
) -> CompletedReply:
    """Normalize the response and recover empty final text without replaying tools."""
    normalized = await output.finish(response.content)
    facts = response_diagnostics(response, normalized=normalized, fallback_model=model)
    response.content = normalized
    attempts = [facts]

    def recovery_state(outcome: str, retries: int):
        return recovery_diagnostics(
            attempts,
            outcome=outcome,
            retries=retries,
            session=session,
            channel=channel,
            iteration=iteration,
        )

    if response.tool_calls:
        if allow_tool_calls:
            return CompletedReply(response, (response,))
        raise EmptyReplyError(recovery_state("unexpected_tool_calls", 0))
    if (response.content or "").strip():
        return CompletedReply(response, (response,))
    if facts["refused"]:
        raise EmptyReplyError(recovery_state("refused", 0))
    logger.warning("[空回复重试] %s", recovery_state("retrying", 0))
    retry_messages = messages + [
        {"role": "assistant", "content": ""},
        {
            "role": "user",
            "content": "你刚才没有给出正式回复。请根据已有结果直接回复用户。",
        },
    ]
    await ensure_request_budget(retry_messages, [], provider, model, max_tokens)
    retry_output = RoleReplyOutput(on_content_delta, enabled=role_reply)
    try:
        retry_response = await provider.chat(
            messages=retry_messages,
            tools=[],
            model=model,
            max_tokens=max_tokens,
            on_content_delta=retry_output.callback,
        )
    except Exception as exc:
        # Recovery failures must not become successful timeout text or history retries.
        raise EmptyReplyError(
            recovery_state("request_failed", 1), request_error=exc
        ) from exc
    normalized = await retry_output.finish(retry_response.content)
    attempts.append(
        response_diagnostics(
            retry_response, normalized=normalized, fallback_model=model
        )
    )
    retry_response.content = normalized
    if retry_response.tool_calls:
        raise EmptyReplyError(recovery_state("unexpected_tool_calls", 1))
    if not (retry_response.content or "").strip():
        outcome = "refused" if attempts[-1]["refused"] else "exhausted"
        raise EmptyReplyError(recovery_state(outcome, 1))
    # Preserve thinking already streamed when recovery does not supply its own.
    retry_response.thinking = retry_response.thinking or response.thinking
    diagnostics = recovery_state("recovered", 1)
    logger.info("[空回复重试] %s", diagnostics)
    return CompletedReply(retry_response, (response, retry_response), diagnostics)
