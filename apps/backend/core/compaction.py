"""One transactional compaction controller for automatic and manual entrypoints."""

from __future__ import annotations

from dataclasses import asdict, dataclass, replace
from typing import Awaitable, Callable, TYPE_CHECKING

from agent.prompting.input_budget import InputBudget
from core.compaction_summary import WorkingSummaryWriter
from session.maintenance_progress import window_key
from session.manager.models import consolidation_cursor

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
    reason: str = "automatic"
    configured_retained_turns: int = 2
    retained_turns: int = 0
    retained_start: int = 0
    snapshot_stop: int = 0
    before_tokens: int = 0
    before_source: str = "local"
    after_source: str | None = None
    after_tokens: int | None = None
    budget: dict | None = None
    window_version: int = 0
    memory_version: int = 0
    memory_cursor: int = 0
    model: str = ""

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
    ) -> None:
        self.sessions = sessions
        self.memory = memory
        self.writer = writer
        self._active: set[str] = set()

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
        reason: str = "automatic",
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
            return await self._ensure(
                session_key=session_key,
                view=view,
                policy=policy,
                message_limit=message_limit,
                budget=budget,
                render=render,
                measure=measure,
                reason=reason,
            )
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
        )
        attempted_stops: set[int] = set()
        for keep in range(min(policy.retained_turns, message_limit), -1, -1):
            prepared = await self.sessions.prepare_window(
                session_key, view, keep_turns=keep, message_limit=message_limit
            )
            if prepared is None or prepared.stop in attempted_stops:
                continue
            attempted_stops.add(prepared.stop)
            state = replace(
                state,
                retained_turns=prepared.retained_turns,
                can_compact=True,
                phase="memory",
                retained_start=prepared.stop,
                snapshot_stop=message_limit,
            )
            try:
                prerequisite = await self.memory.ensure_memory_for_window(prepared)
            except Exception as exc:
                raise CompactionFailedError(
                    replace(state, failure_stage="memory", error=str(exc))
                ) from exc
            current_session = self.sessions.get_or_create(session_key)
            progress = self.sessions.maintenance_progress(current_session)
            state = replace(
                state,
                memory_version=progress.memory_version,
                memory_cursor=consolidation_cursor(
                    current_session, view.scope if view else None
                ),
                window_version=progress.window_versions.get(window_key(view), 0),
            )
            trace = prerequisite.trace
            committed_memory = trace.get("mode") == "markdown" or bool(
                trace.get("memory_committed")
            )
            state = replace(
                state,
                memory_required=state.memory_required or trace.get("mode") != "skipped",
                memory_committed=state.memory_committed or committed_memory,
            )
            if trace.get("mode") == "failed":
                raise CompactionFailedError(
                    replace(
                        state,
                        failure_stage=(
                            "consumers"
                            if trace.get("step") == "consumers"
                            else "memory"
                        ),
                        error=str(trace.get("error", "")),
                    )
                )
            if not trace.get("memory_covered"):
                raise CompactionFailedError(
                    replace(
                        state,
                        failure_stage="memory",
                        error="待移出原文尚未完成记忆整理",
                    )
                )
            state = replace(state, phase="summary")
            try:
                summary = await self.writer.generate(prepared)
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
            )
        raise CompactionFailedError(
            replace(
                state,
                failure_stage="budget",
                error="保留 0 个已完成轮次后仍无法满足目标预算；当前输入、附件和工具交换保持完整",
            )
        )
