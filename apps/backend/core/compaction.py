"""One transactional compaction controller for automatic and manual entrypoints."""

from __future__ import annotations

from dataclasses import asdict, dataclass, replace
from typing import Awaitable, Callable, TYPE_CHECKING

from agent.prompting.input_budget import InputBudget
from agent.prompting.usage_accounting import current_usage
from core.compaction_summary import (
    WorkingSummary,
    WorkingSummaryWriter,
)
from core.compaction_summary_validation import (
    SummaryAttempt,
    SummaryGenerationError,
    validate_summary_limit,
)
from session.maintenance_progress import window_key
from session.manager.models import consolidation_cursor
from shiori_sdk.context import ContextBudgetObserved

NO_COMPLETE_TURNS = "没有可压缩的完整轮次"

if TYPE_CHECKING:
    from conversation.context_scope import ContextView
    from core.memory.markdown import MarkdownMemoryMaintenance
    from session.manager import SessionManager
    from session.manager.window import WindowPreparation


@dataclass(frozen=True)
class CompactionPolicy:
    """Immutable policy captured by one execution; saves affect later executions."""

    retained_turns: int = 2
    summary_token_limit: int = 2000

    def __post_init__(self) -> None:
        validate_summary_limit(self.summary_token_limit)
        if type(self.retained_turns) is not int or self.retained_turns < 0:
            raise ValueError("压缩后保留原文轮数必须是非负整数")


@dataclass(frozen=True)
class CompactionResult:
    """Shared staged outcome; committed memory is never rolled back by a failed window."""

    committed: bool = False
    phase: str = "idle"
    can_compact: bool = False
    memory_required: bool = False
    memory_committed: bool = False
    failure_stage: str = ""
    error: str = ""
    reason: str = "auto_threshold"
    configured_retained_turns: int = 2
    retained_turns: int = 0
    retained_start: int = 0
    snapshot_stop: int = 0
    before_tokens: int | None = None
    before_source: str | None = None
    after_source: str | None = None
    after_tokens: int | None = None
    budget: dict | None = None
    window_version: int = 0
    memory_version: int = 0
    memory_cursor: int = 0
    model: str = ""
    attempts: int = 0
    compaction_count: int = 0
    retained_reduction_reason: str = ""
    memory_start: int | None = None
    memory_stop: int | None = None
    memory_status: str = "not_required"
    window_start: int = 0
    published_version: int = 0
    relationship_version: int = 0
    degraded: bool = False
    degradation_attempts: int = 0
    removed_categories: tuple[str, ...] = ()
    tools_disabled: bool = False
    failure_kind: str = ""
    final_budget: dict | None = None
    generation: int = 0
    ownership: str = ""
    summary_diagnostics: tuple[SummaryAttempt, ...] = ()

    def dump(self) -> dict:
        """Serializable state shared by request traces, desktop, and commands."""
        return asdict(self)


class CompactionFailedError(RuntimeError):
    """An explicit terminal request failure, deliberately not a tool-replay retry."""

    def __init__(self, result: CompactionResult) -> None:
        self.result = replace(result, phase="failed")
        super().__init__(
            f"上下文压缩失败：stage={result.failure_stage}, memory_committed={result.memory_committed}; {result.error}"
        )


class CompactionController:
    """Own the memory → working state → fully rendered validation → atomic cut flow."""

    def __init__(
        self,
        sessions: SessionManager,
        memory: MarkdownMemoryMaintenance,
        writer: WorkingSummaryWriter,
        observe: Callable[[ContextBudgetObserved], Awaitable[object]] | None = None,
    ) -> None:
        self.sessions = sessions
        self.memory = memory
        self.writer = writer
        self._active: set[str] = set()
        self._observe = observe
        # Observations carry (ownership, generation): an unpersisted rebinding can
        # reuse a generation number under another ownership.
        self._latest: dict[tuple[str, str], tuple[str, int, dict]] = {}
        self._latest_compaction: dict[tuple[str, str], tuple[str, int, dict]] = {}

    def latest(
        self, session_key: str, view: ContextView | None, *, request: bool = False
    ) -> dict | None:
        """Return only observations still owned by the current binding and generation.

        Windows are model independent, so a model switch keeps observations.
        """
        progress = self.sessions.maintenance_progress(
            self.sessions.get_or_create(session_key)
        )
        key = window_key(view)
        stored = (self._latest if request else self._latest_compaction).get(
            (session_key, key)
        )
        if stored and stored[:2] == (progress.ownership, progress.generation):
            return dict(stored[2])
        return None

    async def record(
        self,
        session_key: str,
        view: ContextView | None,
        result: CompactionResult,
        *,
        request_usage: dict | None = None,
        request_attempted: bool = False,
    ) -> None:
        """Publish facts; only the provider boundary may replace the last request."""
        progress = self.sessions.maintenance_progress(
            self.sessions.get_or_create(session_key)
        )
        payload = result.dump()
        # Exception messages may contain provider payloads; observations need the
        # classified stage/kind only, never user text, tool arguments or Base64.
        payload.pop("error", None)
        payload["request_usage"] = (
            request_usage if request_usage is not None else current_usage()
        )
        key = window_key(view)
        if (result.ownership, result.generation) == (
            progress.ownership,
            progress.generation,
        ):
            observation = (result.ownership, result.generation, payload)
            if request_attempted:
                self._latest[(session_key, key)] = observation
            if result.phase != "request":
                self._latest_compaction[(session_key, key)] = observation
        if self._observe is not None:
            await self._observe(ContextBudgetObserved(session_key, key, payload))

    def is_busy(self, session_key: str) -> bool:
        """Report the controller gate, including sessions without a role runtime."""
        return session_key in self._active

    async def ensure(
        self,
        *,
        session_key: str,
        view: ContextView | None,
        policy: CompactionPolicy,
        message_limit: int,
        budget: InputBudget,
        render: Callable[[WindowPreparation, str], Awaitable[list[dict]]],
        measure: Callable[[list[dict]], InputBudget],
        reason: str = "auto_threshold",
        render_minimal: Callable[[str], Awaitable[list[dict]]] | None = None,
        minimal_only: bool = False,
        prior_result: CompactionResult | None = None,
    ) -> tuple[list[dict], CompactionResult]:
        """Reject repeated work before memory extraction or summary generation."""
        if self.is_busy(session_key):
            raise CompactionFailedError(
                CompactionResult(
                    failure_stage="busy",
                    error="上下文正在压缩，请稍后重试",
                    reason=reason,
                )
            )
        self._active.add(session_key)
        try:
            messages, result = await self._ensure(
                session_key=session_key,
                view=view,
                policy=policy,
                message_limit=message_limit,
                budget=budget,
                render=render,
                measure=measure,
                reason=reason,
                render_minimal=render_minimal,
                minimal_only=minimal_only,
                prior_result=prior_result,
            )
            await self.record(session_key, view, result)
            return messages, result
        except CompactionFailedError as exc:
            await self.record(session_key, view, exc.result)
            raise
        finally:
            self._active.remove(session_key)

    async def _ensure(
        self,
        *,
        session_key: str,
        view: ContextView | None,
        policy: CompactionPolicy,
        message_limit: int,
        budget: InputBudget,
        render: Callable[[WindowPreparation, str], Awaitable[list[dict]]],
        measure: Callable[[list[dict]], InputBudget],
        reason: str,
        render_minimal: Callable[[str], Awaitable[list[dict]]] | None,
        minimal_only: bool,
        prior_result: CompactionResult | None,
    ) -> tuple[list[dict], CompactionResult]:
        """Try successively fewer complete turns; never publish an over-budget draft."""
        state = CompactionResult(
            reason=reason,
            configured_retained_turns=policy.retained_turns,
            before_tokens=budget.estimate.tokens,
            before_source=budget.estimate.source,
            phase="preparing",
            budget=asdict(budget),
            model=self.writer.model_name,
            memory_committed=bool(prior_result and prior_result.memory_committed),
            memory_required=bool(prior_result and prior_result.memory_required),
        )
        progress = self.sessions.maintenance_progress(
            self.sessions.get_or_create(session_key)
        )
        state = self.progress_result(
            replace(
                state,
                generation=(
                    prior_result.generation if prior_result else progress.generation
                ),
                ownership=(
                    prior_result.ownership if prior_result else progress.ownership
                ),
            ),
            session_key,
            view,
        )
        summary_content = progress.summaries.get(window_key(view), "")
        self._assert_owner(state, session_key, view)
        chosen = (
            None
            if minimal_only
            else await self._choose_retention(
                state,
                session_key,
                view,
                policy=policy,
                message_limit=message_limit,
                render=render,
                measure=measure,
                manual=reason == "manual",
            )
        )
        if chosen is None and reason == "manual":
            # Manual compaction never goes below the configured retention just
            # because nothing older is left; only the budget may reduce it.
            raise CompactionFailedError(
                replace(
                    state,
                    failure_stage="no_turns",
                    error=NO_COMPLETE_TURNS,
                )
            )
        if chosen is not None:
            prepared, reduced = chosen
            state = replace(state, snapshot_stop=message_limit)
            state, summary, messages = await self._attempt(
                state, prepared, render, measure, reduced=reduced
            )
            summary_content = summary.content
            if not _fits(state) and prepared.retained_turns > 0:
                # The estimate was wrong: measure once more with zero turns,
                # extending memory and regenerating the summary for that range.
                fewest = await self._prepare(
                    state, session_key, view, keep_turns=0, message_limit=message_limit
                )
                if fewest is not None and fewest.stop != prepared.stop:
                    prepared = fewest
                    state, summary, messages = await self._attempt(
                        state, prepared, render, measure, reduced=True
                    )
                    summary_content = summary.content
            # The target line is the ideal; only the hard input limit fails.
            if _fits(state):
                return messages, await self._commit(
                    state, prepared, summary, session_key, view
                )
        if render_minimal is not None and reason != "manual":
            return await self._minimal(
                state,
                session_key,
                view,
                message_limit,
                summary_content,
                render_minimal,
                measure,
            )
        raise CompactionFailedError(
            replace(
                state,
                failure_stage="budget",
                failure_kind="local_budget",
                error=(
                    f"保留 {state.retained_turns} 个已完成轮次后仍超出模型输入上限；"
                    "当前输入、附件和工具交换保持完整"
                ),
            )
        )

    async def _attempt(
        self,
        state: CompactionResult,
        prepared: WindowPreparation,
        render: Callable[[WindowPreparation, str], Awaitable[list[dict]]],
        measure: Callable[[list[dict]], InputBudget],
        *,
        reduced: bool,
    ):
        """Commit memory, generate one summary and measure the rendered request."""
        state = replace(
            state,
            retained_turns=prepared.retained_turns,
            can_compact=True,
            phase="memory",
            retained_start=prepared.stop,
            attempts=state.attempts + 1,
            retained_reduction_reason="budget" if reduced else "",
        )
        state = await self._memory(state, prepared)
        state = replace(state, phase="summary")
        summary, state = await self._summary(state, prepared)
        try:
            messages = await render(prepared, summary.content)
            after = measure(messages)
        except Exception as exc:
            raise CompactionFailedError(
                replace(state, failure_stage="validation", error=str(exc))
            ) from exc
        state = replace(
            state,
            phase="validation",
            after_tokens=after.estimate.tokens,
            after_source=after.estimate.source,
            final_budget=asdict(after),
        )
        return state, summary, messages

    async def _summary(self, state: CompactionResult, prepared: WindowPreparation):
        """Keep diagnostics with this execution, including failed shortening attempts."""
        try:
            summary = await self.writer.generate(prepared)
        except Exception as exc:
            diagnostics = (
                exc.diagnostics if isinstance(exc, SummaryGenerationError) else ()
            )
            raise CompactionFailedError(
                replace(
                    state,
                    failure_stage="summary",
                    error=str(exc),
                    summary_diagnostics=state.summary_diagnostics + diagnostics,
                )
            ) from exc
        return summary, replace(
            state, summary_diagnostics=state.summary_diagnostics + summary.diagnostics
        )

    async def _choose_retention(
        self,
        state: CompactionResult,
        session_key: str,
        view: ContextView | None,
        *,
        policy: CompactionPolicy,
        message_limit: int,
        render: Callable[[WindowPreparation, str], Awaitable[list[dict]]],
        measure: Callable[[list[dict]], InputBudget],
        manual: bool = False,
    ):
        """Pick one retention by local estimate, before any memory or summary work.

        Each candidate renders without a summary, then adds the summary's token
        configured allowance. This is only a projection: the actual summary is
        rendered and measured before any commit. The first count projected below
        the target wins; otherwise the largest count projected below the hard
        input limit; otherwise the fewest turns, left to the measured result.
        Returns the preparation and whether it retains fewer turns than the first.
        A manual run keeps the configured count whenever it fits the hard limit,
        and returns None when the configured retention removes nothing.
        """

        def acceptable(tokens: int, projected: InputBudget) -> bool:
            # Manual runs only reduce retention when the budget truly requires it.
            line = projected.input_limit_tokens if manual else projected.target_tokens
            return tokens < line

        candidates: list[tuple[WindowPreparation, int, InputBudget]] = []
        seen: set[int] = set()
        configured = min(policy.retained_turns, message_limit)
        for keep in range(configured, -1, -1):
            prepared = await self._prepare(
                state, session_key, view, keep_turns=keep, message_limit=message_limit
            )
            if prepared is None and manual and keep == configured:
                return None
            if prepared is None or prepared.stop in seen:
                continue
            self._assert_owner(state, session_key, view)
            seen.add(prepared.stop)
            try:
                projected = measure(await render(prepared, ""))
            except Exception as exc:
                raise CompactionFailedError(
                    replace(state, failure_stage="validation", error=str(exc))
                ) from exc
            tokens = projected.estimate.tokens + policy.summary_token_limit
            candidates.append((prepared, tokens, projected))
            if acceptable(tokens, projected):
                break
        if not candidates:
            return None
        first = candidates[0][0]
        fits = [
            prepared
            for prepared, tokens, projected in candidates
            if acceptable(tokens, projected)
        ] or [
            prepared
            for prepared, tokens, projected in candidates
            if tokens < projected.input_limit_tokens
        ]
        chosen = fits[0] if fits else candidates[-1][0]
        return chosen, chosen is not first

    async def _commit(
        self,
        state: CompactionResult,
        prepared: WindowPreparation,
        summary: WorkingSummary,
        session_key: str,
        view: ContextView | None,
    ):
        """Publish the validated summary and cut together, or fail the window stage."""
        try:
            committed = await self.sessions.commit_window(
                prepared, summary.content, summary.source_ids
            )
        except Exception as exc:
            raise CompactionFailedError(
                replace(state, failure_stage="window", error=str(exc))
            ) from exc
        if not committed:
            raise CompactionFailedError(
                replace(
                    state,
                    failure_stage="window",
                    error="窗口准备已过期或记忆覆盖不完整",
                )
            )
        progress = self.sessions.maintenance_progress(
            self.sessions.get_or_create(session_key)
        )
        return replace(
            state,
            committed=True,
            phase="completed",
            window_version=progress.window_versions[window_key(view)],
            memory_version=progress.memory_version,
            compaction_count=state.compaction_count + 1,
            window_start=prepared.stop,
        )

    def progress_result(
        self, state: CompactionResult, session_key: str, view: ContextView | None
    ):
        """Attach actual independent memory/window progress to a request outcome."""
        session = self.sessions.get_or_create(session_key)
        progress = self.sessions.maintenance_progress(session)
        return replace(
            state,
            memory_version=progress.memory_version,
            memory_cursor=consolidation_cursor(session, view.scope if view else None),
            window_version=progress.window_versions.get(window_key(view), 0),
            window_start=progress.cursor(view),
            published_version=progress.published_version,
            relationship_version=progress.relationship_version,
            compaction_count=progress.compaction_counts.get(window_key(view), 0),
        )

    async def _memory(self, state: CompactionResult, prepared: WindowPreparation):
        self._assert_owner(state, prepared.session_key, prepared.view)
        state = replace(
            state,
            phase="memory",
            memory_start=prepared.start,
            memory_stop=prepared.stop,
            memory_status="uncommitted",
        )
        try:
            prerequisite = await self.memory.ensure_memory_for_window(prepared)
        except Exception as exc:
            state = self.progress_result(state, prepared.session_key, prepared.view)
            raise CompactionFailedError(
                replace(state, failure_stage="memory", error=str(exc))
            ) from exc
        state = self.progress_result(state, prepared.session_key, prepared.view)
        trace = prerequisite.trace
        committed = (
            state.memory_committed
            or trace.get("mode") == "markdown"
            or bool(trace.get("memory_committed"))
        )
        state = replace(
            state,
            memory_required=state.memory_required or trace.get("mode") != "skipped",
            memory_committed=committed,
            memory_status="committed" if committed else "covered",
        )
        consumers = trace.get("step") == "consumers"
        # Downstream consumers (relationship snapshots) retry on their own; only
        # uncovered memory for the removed range blocks the window.
        if not trace.get("memory_covered") or (
            trace.get("mode") == "failed" and not consumers
        ):
            raise CompactionFailedError(
                replace(
                    state,
                    failure_stage="consumers" if consumers else "memory",
                    memory_status=(
                        "consumer_failed"
                        if consumers
                        else ("committed" if committed else "uncommitted")
                    ),
                    error=str(trace.get("error") or "待移出原文尚未完成记忆整理"),
                )
            )
        return state

    async def _prepare(
        self,
        state: CompactionResult,
        session_key: str,
        view: ContextView | None,
        **kwargs,
    ):
        try:
            return await self.sessions.prepare_window(session_key, view, **kwargs)
        except Exception as exc:
            raise CompactionFailedError(
                replace(state, failure_stage="preparation", error=str(exc))
            ) from exc

    def _assert_owner(
        self, state: CompactionResult, session_key: str, view: ContextView | None
    ) -> None:
        progress = self.sessions.maintenance_progress(
            self.sessions.get_or_create(session_key)
        )
        if (
            progress.generation != state.generation
            or progress.ownership != state.ownership
        ):
            raise CompactionFailedError(
                replace(state, failure_stage="window", error="请求归属已变化")
            )

    async def _minimal(
        self,
        state: CompactionResult,
        session_key: str,
        view: ContextView | None,
        message_limit: int,
        summary: str,
        render: Callable[[str], Awaitable[list[dict]]],
        measure: Callable[[list[dict]], InputBudget],
    ) -> tuple[list[dict], CompactionResult]:
        state = replace(
            state,
            phase="minimal",
            degradation_attempts=1,
            retained_turns=0,
            retained_start=message_limit,
            snapshot_stop=message_limit,
            retained_reduction_reason="minimal_request",
            tools_disabled=True,
            removed_categories=(
                "history",
                "retrieval",
                "optional_injections",
                "tool_schemas",
                "tool_call_arguments",
            ),
        )
        prepared = await self._prepare(
            state,
            session_key,
            view,
            keep_turns=0,
            message_limit=message_limit,
            request_only=True,
        )
        if prepared is not None:
            summarized_stop = state.memory_stop
            state = await self._memory(state, prepared)
            if summarized_stop != prepared.stop or not summary:
                generated, state = await self._summary(state, prepared)
                summary = generated.content
        try:
            messages = await render(summary)
            final = measure(messages)
        except Exception as exc:
            raise CompactionFailedError(
                replace(state, failure_stage="minimal_preparation", error=str(exc))
            ) from exc
        state = replace(
            state,
            phase="minimal",
            after_tokens=final.estimate.tokens,
            after_source=final.estimate.source,
            final_budget=asdict(final),
        )
        self._assert_owner(state, session_key, view)
        if prepared is not None and not await self.sessions.validate_request_window(
            prepared
        ):
            raise CompactionFailedError(
                replace(state, failure_stage="window", error="最小请求准备已过期")
            )
        if final.estimate.tokens >= final.input_limit_tokens:
            raise CompactionFailedError(
                replace(
                    state,
                    failure_stage="minimal_budget",
                    failure_kind="local_budget",
                    error="必要系统约束、当前输入、附件及必要工具结果仍超出模型输入预算",
                )
            )
        return messages, replace(state, degraded=True, phase="degraded")


def _fits(state: CompactionResult):
    """The measured request is below the hard input limit."""
    final = state.final_budget or {}
    return (state.after_tokens or 0) < final.get("input_limit_tokens", 0)
