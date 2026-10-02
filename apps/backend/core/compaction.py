"""One transactional compaction controller for automatic and manual entrypoints."""

from __future__ import annotations

from dataclasses import asdict, dataclass, replace
from typing import Awaitable, Callable, TYPE_CHECKING

from agent.prompting.input_budget import InputBudget
from agent.prompting.usage_accounting import current_usage
from core.compaction_summary import WorkingSummaryWriter
from session.maintenance_progress import window_key
from session.manager.models import consolidation_cursor
from shiori_sdk.context import ContextBudgetObserved

if TYPE_CHECKING:
    from conversation.context_scope import ContextView
    from core.memory.markdown import MarkdownMemoryMaintenance
    from session.manager import SessionManager
    from session.manager.window import WindowPreparation


@dataclass(frozen=True)
class CompactionPolicy:
    """Immutable policy captured by one execution; saves affect later executions."""

    retained_turns: int = 2

    def __post_init__(self) -> None:
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
        attempted_stops: set[int] = set()
        for keep in (
            []
            if minimal_only
            else range(min(policy.retained_turns, message_limit), -1, -1)
        ):
            prepared = await self._prepare(
                state, session_key, view, keep_turns=keep, message_limit=message_limit
            )
            if prepared is None or prepared.stop in attempted_stops:
                continue
            self._assert_owner(state, session_key, view)
            attempted_stops.add(prepared.stop)
            state = replace(
                state,
                retained_turns=prepared.retained_turns,
                can_compact=True,
                phase="memory",
                retained_start=prepared.stop,
                snapshot_stop=message_limit,
                attempts=state.attempts + 1,
                retained_reduction_reason=(
                    "budget" if len(attempted_stops) > 1 else ""
                ),
            )
            state = await self._memory(state, prepared)
            state = replace(state, phase="summary")
            try:
                summary = await self.writer.generate(prepared)
                summary_content = summary.content
            except Exception as exc:
                raise CompactionFailedError(
                    replace(state, failure_stage="summary", error=str(exc))
                ) from exc
            try:
                messages = await render(prepared, summary.content)
                after = measure(messages)
                state = replace(
                    state,
                    phase="validation",
                    after_tokens=after.estimate.tokens,
                    after_source=after.estimate.source,
                    final_budget=asdict(after),
                )
            except Exception as exc:
                raise CompactionFailedError(
                    replace(state, failure_stage="validation", error=str(exc))
                ) from exc
            if after.estimate.tokens >= after.target_tokens:
                continue
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
            return messages, replace(
                state,
                committed=True,
                phase="completed",
                window_version=progress.window_versions[window_key(view)],
                memory_version=progress.memory_version,
                compaction_count=state.compaction_count + 1,
                window_start=prepared.stop,
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
                error="保留 0 个已完成轮次后仍无法满足目标预算；当前输入、附件和工具交换保持完整",
            )
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
        if trace.get("mode") == "failed" or not trace.get("memory_covered"):
            consumers = trace.get("step") == "consumers"
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
                try:
                    summary = (await self.writer.generate(prepared)).content
                except Exception as exc:
                    raise CompactionFailedError(
                        replace(state, failure_stage="summary", error=str(exc))
                    ) from exc
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
