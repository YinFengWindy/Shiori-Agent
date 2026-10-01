"""Transitional raw-window maintenance with a mandatory memory prerequisite.

This uses the existing retention policy. Bounded summaries and the final shared
controller belong to the next stage; memory scheduling remains independent.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from agent.core.passive_support import estimate_messages_tokens
from conversation.context_scope import history_start, history_filter

if TYPE_CHECKING:
    from conversation.context_scope import ContextView
    from core.memory.markdown import MarkdownMemoryMaintenance
    from session.manager import SessionManager
    from session.manager.window import WindowPreparation


@dataclass(frozen=True)
class WindowMaintenanceResult:
    """Independent stages: a failed window never implies rollback of memory."""

    committed: bool
    memory_committed: bool = False
    failure_stage: str = ""
    error: str = ""


class WindowMaintenanceFailedError(RuntimeError):
    """Expose the failed stage and committed-memory fact to the actual turn caller."""

    def __init__(self, result: WindowMaintenanceResult) -> None:
        self.result = result
        super().__init__(
            f"窗口维护失败：stage={result.failure_stage}, "
            f"memory_committed={result.memory_committed}; {result.error}"
        )


class ContextWindowMaintenance:
    """Coordinate the session window owner and memory prerequisite owner."""

    def __init__(
        self,
        sessions: SessionManager,
        memory: MarkdownMemoryMaintenance,
    ) -> None:
        self.sessions = sessions
        self.memory = memory

    async def apply(self, prepared: WindowPreparation) -> WindowMaintenanceResult:
        """Ensure exactly the required memory range, then conditionally publish cut."""
        try:
            result = await self.memory.ensure_memory_for_window(prepared)
        except Exception as exc:
            return WindowMaintenanceResult(False, False, "memory", str(exc))
        committed_memory = result.trace.get("mode") == "markdown" or bool(
            result.trace.get("memory_committed")
        )
        if result.trace.get("mode") == "failed":
            return WindowMaintenanceResult(
                False,
                committed_memory,
                "consumers" if result.trace.get("step") == "consumers" else "memory",
                str(result.trace.get("error", "")),
            )
        try:
            committed = await self.sessions.commit_window(prepared)
        except Exception as exc:
            return WindowMaintenanceResult(False, committed_memory, "window", str(exc))
        return WindowMaintenanceResult(
            committed,
            committed_memory,
            "" if committed else "window",
        )

    async def ensure_budget(
        self,
        session_key: str,
        current_content: str,
        view: ContextView | None,
        *,
        keep_count: int,
        input_token_threshold: int,
    ) -> bool:
        """Apply the existing two-pass window policy after final-request pressure."""
        for force in (False, True):
            prepared = await self.sessions.prepare_window(
                session_key,
                view,
                keep_count=keep_count,
                force=force,
            )
            if prepared is not None:
                result = await self.apply(prepared)
                if not result.committed:
                    raise WindowMaintenanceFailedError(result)
            session = self.sessions.get_or_create(session_key)
            history = session.get_history(
                start_index=history_start(session, view),
                include=history_filter(view),
            )
            tokens = estimate_messages_tokens(
                [
                    *history,
                    {"role": "user", "content": current_content},
                ]
            )
            if tokens < input_token_threshold:
                return True
        return False
