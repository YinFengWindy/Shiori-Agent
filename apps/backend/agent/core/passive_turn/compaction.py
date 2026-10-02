"""Execution-local request guard; current input and live tool exchanges stay intact."""

from __future__ import annotations

from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import asdict, dataclass, field, replace
from typing import Awaitable, Callable, TYPE_CHECKING

from core.compaction import (
    CompactionController,
    CompactionFailedError,
    CompactionPolicy,
    CompactionResult,
)
from agent.provider import LLMProvider
from agent.prompting.usage_accounting import current_usage
from session.maintenance_progress import window_key
from .minimal_request import completed_tool_results

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
    render_minimal: Callable[[str], Awaitable[list[dict]]] | None = None
    degraded: bool = False
    tools_started: bool = False
    last_result: CompactionResult | None = None

    def __post_init__(self) -> None:
        progress = self.controller.sessions.maintenance_progress(
            self.controller.sessions.get_or_create(self.session_key)
        )
        self.last_result = self.controller.progress_result(
            CompactionResult(
                request_owner=progress.request_owners.get(window_key(self.view), ""),
                generation=progress.generation,
                ownership=progress.ownership,
                reason="",
                configured_retained_turns=self.policy.retained_turns,
                snapshot_stop=self.message_limit,
            ),
            self.session_key,
            self.view,
        )

    async def ensure(
        self,
        messages: list[dict],
        schemas: list[dict],
        provider: LLMProvider,
        model: str,
        max_tokens: int,
        purpose: str,
        schemas_for_history: Callable[[list[str]], list[dict]] | None = None,
        *,
        force: bool = False,
        minimal_only: bool = False,
    ) -> None:
        """Re-render only persisted history; carry the exact current-turn suffix along."""

        if self.degraded:
            schemas.clear()
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
        if budget is None:
            return
        if not force and (
            not budget.needs_trim
            or (self.degraded and budget.estimate.tokens < budget.input_limit_tokens)
        ):
            self.last_result = replace(
                self.last_result
                or CompactionResult(model=provider.context_model(model)),
                phase="request",
                model=provider.context_model(model),
                budget=asdict(budget),
                final_budget=asdict(budget),
                after_tokens=budget.estimate.tokens,
                after_source=budget.estimate.source,
            )
            return
        tail = messages[self.prefix_length :]
        next_prefix_length = self.prefix_length
        self.tools_started = self.tools_started or any(
            m.get("tool_calls") for m in tail
        )

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

        async def render_minimal(summary: str):
            nonlocal next_prefix_length, candidate_schemas
            assert self.render_minimal is not None
            candidate_schemas = []
            prefix = await self.render_minimal(summary)
            next_prefix_length = len(prefix)
            return [*prefix, *completed_tool_results(tail)]

        if self.degraded:
            failure = CompactionFailedError(
                replace(
                    self.last_result or CompactionResult(),
                    failure_stage="minimal_budget",
                    failure_kind="local_budget",
                    error="最小请求已超出输入预算",
                    final_budget=asdict(budget),
                    after_tokens=budget.estimate.tokens,
                    after_source=budget.estimate.source,
                )
            )
            self.last_result = failure.result
            self.results.append(failure.result.dump())
            await self.controller.record(self.session_key, self.view, failure.result)
            raise failure

        try:
            candidate, result = await self.controller.ensure(
                session_key=self.session_key,
                view=self.view,
                policy=self.policy,
                message_limit=self.message_limit,
                budget=budget,
                render=render,
                measure=measure,
                reason=(
                    "hard_limit"
                    if force or budget.estimate.tokens >= budget.input_limit_tokens
                    else "auto_threshold"
                ),
                render_minimal=(
                    render_minimal if self.render_minimal is not None else None
                ),
                minimal_only=minimal_only,
                prior_result=self.last_result,
            )
        except CompactionFailedError as exc:
            self.results.append(exc.result.dump())
            raise
        messages[:] = candidate
        schemas[:] = candidate_schemas
        self.prefix_length = next_prefix_length
        self.degraded = result.degraded
        self.last_result = result
        self.results.append(result.dump())

    async def observe_request(
        self,
        budget,
        *,
        error: BaseException | None = None,
        failure_stage: str = "provider",
        request_attempted: bool = True,
    ):
        """Record the actual final request and staged failure, with no payload text."""
        from agent.provider import ContextLengthError, LocalBudgetExceeded

        result = self.last_result or CompactionResult()
        if budget is not None:
            result = replace(
                result,
                final_budget=asdict(budget),
                after_tokens=budget.estimate.tokens,
                after_source=budget.estimate.source,
            )
        if error is not None:
            result = replace(
                result,
                phase="failed",
                failure_stage=failure_stage,
                failure_kind=(
                    "response_error"
                    if failure_stage == "response"
                    else (
                        "local_budget"
                        if isinstance(error, LocalBudgetExceeded)
                        else (
                            "provider_context_length"
                            if isinstance(error, ContextLengthError)
                            else "provider_error"
                        )
                    )
                ),
                error=str(error),
            )
        self.last_result = result
        await self.controller.record(
            self.session_key,
            self.view,
            result,
            request_usage=current_usage(),
            request_attempted=request_attempted,
        )
        return result


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


def request_tools_disabled() -> bool:
    """A degraded request cannot execute unsolicited provider tool calls."""
    scope = _current.get()
    return scope is not None and scope.degraded


def current_request_compaction() -> RequestCompaction | None:
    """Return the isolated request owner to the provider-call boundary."""
    return _current.get()


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
