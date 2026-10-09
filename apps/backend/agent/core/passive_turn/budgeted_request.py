"""Bounded provider recovery at one request boundary, never at the tool loop."""

import logging

from agent.context import without_attachment_tool_hints
from agent.provider import LLMProvider
from agent.prompting.usage_accounting import current_usage, mark_speaking_request
from core.compaction import CompactionFailedError
from .compaction import current_request_compaction

logger = logging.getLogger("agent.budgeted_request")


async def budgeted_chat(provider: LLMProvider, **kwargs):
    """Send at most three requests: original, ordinary compaction, one minimal.

    Only a real provider context rejection retries this exact request boundary.
    Tool execution lives outside it, so no completed side effects can replay.
    """
    from agent.provider import ContextLengthError, LocalBudgetExceeded

    def prepare_messages():
        # Finalization has no reader tools; a compaction retry may also disable
        # them or re-render the original attachment instructions. Preserve paths
        # and user prose while removing only the host-generated reader hints.
        if not kwargs.get("tools") or kwargs.get("tool_choice") == "none":
            kwargs["messages"][:] = [
                (
                    without_attachment_tool_hints(message)
                    if message.get("role") == "user"
                    else message
                )
                for message in kwargs["messages"]
            ]

    scope = current_request_compaction()
    if scope is None or not isinstance(provider, LLMProvider):
        prepare_messages()
        return await provider.chat(**kwargs)
    for attempt in range(3):
        prepare_messages()
        previous_calls = len(current_usage()["calls"])
        try:
            response = await provider.chat(**kwargs)
        except Exception as exc:
            mark_speaking_request(after=previous_calls)
            if not isinstance(exc, ContextLengthError):
                # Provider, network, timeout and safety failures are not budget
                # failures; the pipeline's error boundary owns them unchanged.
                try:
                    await scope.observe_request(None, error=exc)
                except Exception:
                    # Observation is secondary; it must not mask the provider error.
                    logger.exception("记录请求失败观测时出错")
                raise exc
            result = await scope.observe_request(
                None,
                error=exc,
                request_attempted=not isinstance(exc, LocalBudgetExceeded),
            )
            if (
                not isinstance(exc, LocalBudgetExceeded)
                and not scope.degraded
                and attempt < 2
            ):
                await scope.ensure(
                    kwargs["messages"],
                    kwargs.get("tools") or [],
                    provider,
                    kwargs["model"],
                    kwargs["max_tokens"],
                    kwargs.get("call_purpose", "default"),
                    force=True,
                    minimal_only=attempt == 1,
                )
                if scope.degraded:
                    kwargs["tools"] = []
                continue
            raise CompactionFailedError(result) from exc
        mark_speaking_request(after=previous_calls)
        budget = response.input_budget or provider.input_budget(
            messages=kwargs["messages"],
            tools=kwargs.get("tools"),
            model=kwargs["model"],
            max_tokens=kwargs["max_tokens"],
            call_purpose=kwargs.get("call_purpose", "default"),
        )
        if scope.degraded and response.tool_calls:
            result = await scope.observe_request(
                budget,
                error=RuntimeError("本次工具已禁用，但模型仍返回工具调用"),
                failure_stage="response",
            )
            raise CompactionFailedError(result)
        await scope.observe_request(budget)
        return response
    raise AssertionError("bounded request loop exhausted")
