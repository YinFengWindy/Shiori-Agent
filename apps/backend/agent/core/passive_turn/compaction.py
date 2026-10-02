"""Execution-local request guard; current input and live tool exchanges stay intact."""

from __future__ import annotations

from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass, field
from typing import Awaitable, Callable, TYPE_CHECKING

from core.compaction import (
    CompactionController,
    CompactionFailedError,
    CompactionPolicy,
    CompactionResult,
)
from agent.provider import LLMProvider

if TYPE_CHECKING:
    from conversation.context_scope import ContextView
    from session.manager.window import WindowPreparation


@dataclass
class RequestCompaction:
    """Immutable policy and persisted prefix, with a mutable current request boundary."""

    controller: CompactionController
    session_key: str
    view: ContextView | None
    policy: CompactionPolicy
    message_limit: int
    prefix_length: int
    render: Callable[[WindowPreparation, str, list[str]], Awaitable[list[dict]]]
    history_tools: Callable[[WindowPreparation], list[str]]
    results: list[dict] = field(default_factory=list)

    async def ensure(
        self,
        messages: list[dict],
        schemas: list[dict],
        provider: LLMProvider,
        model: str,
        max_tokens: int,
        purpose: str,
        schemas_for_history: Callable[[list[str]], list[dict]] | None = None,
    ) -> None:
        """Re-render only persisted history; carry the exact current-turn suffix along."""

        candidate_schemas = schemas

        def measure(candidate: list[dict]):
            budget = provider.input_budget(
                messages=candidate,
                tools=candidate_schemas,
                model=model,
                max_tokens=max_tokens,
                call_purpose=purpose,
            )
            if budget is None:
                raise ValueError("压缩请求缺少模型预算")
            return budget

        budget = provider.input_budget(
            messages=messages,
            tools=schemas,
            model=model,
            max_tokens=max_tokens,
            call_purpose=purpose,
        )
        if budget is None or not budget.needs_trim:
            return
        tail = messages[self.prefix_length :]
        next_prefix_length = self.prefix_length

        async def render(prepared: WindowPreparation, summary: str):
            nonlocal next_prefix_length, candidate_schemas
            candidate_schemas = (
                schemas_for_history(self.history_tools(prepared))
                if schemas_for_history is not None
                else schemas
            )
            names = [schema["function"]["name"] for schema in candidate_schemas]
            prefix = await self.render(prepared, summary, names)
            next_prefix_length = len(prefix)
            return [*prefix, *tail]

        try:
            candidate, result = await self.controller.ensure(
                session_key=self.session_key,
                view=self.view,
                policy=self.policy,
                message_limit=self.message_limit,
                budget=budget,
                render=render,
                measure=measure,
            )
        except CompactionFailedError as exc:
            self.results.append(exc.result.dump())
            raise
        messages[:] = candidate
        schemas[:] = candidate_schemas
        self.prefix_length = next_prefix_length
        self.results.append(result.dump())


_current: ContextVar[RequestCompaction | None] = ContextVar(
    "request_compaction", default=None
)


@contextmanager
def request_compaction_scope(scope: RequestCompaction | None):
    """Isolate concurrent turns and nested executions from each other's callbacks."""
    token = _current.set(scope)
    try:
        yield
    finally:
        _current.reset(token)


async def ensure_request_budget(
    messages: list[dict],
    schemas: list[dict],
    provider: LLMProvider,
    model: str,
    max_tokens: int,
    *,
    purpose: str = "default",
    schemas_for_history: Callable[[list[str]], list[dict]] | None = None,
) -> None:
    """Guard every rendered speaking request, including recovery and finalization."""
    if not isinstance(provider, LLMProvider):
        return
    scope = _current.get()
    if scope is not None:
        await scope.ensure(
            messages, schemas, provider, model, max_tokens, purpose, schemas_for_history
        )
        return
    budget = provider.input_budget(
        messages=messages,
        tools=schemas,
        model=model,
        max_tokens=max_tokens,
        call_purpose=purpose,
    )
    if budget is not None and budget.needs_trim:
        raise CompactionFailedError(
            CompactionResult(
                failure_stage="budget",
                error="当前请求没有可压缩的会话窗口",
                before_tokens=budget.estimate.tokens,
            )
        )


def with_working_summary(messages: list[dict], summary: str) -> list[dict]:
    """Render working state as a distinct system block beside semantic memory."""
    if not summary:
        return messages
    state = {
        "role": "system",
        "content": "[working_state]\n" + summary + "\n[/working_state]",
    }
    if messages and messages[0].get("role") == "system":
        return [messages[0], state, *messages[1:]]
    return [state, *messages]
