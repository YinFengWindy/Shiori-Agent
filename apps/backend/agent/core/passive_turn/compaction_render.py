"""Render a candidate persisted window with fresh sources and the exact current input."""

from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass, replace
from typing import Awaitable, Callable, TYPE_CHECKING

from agent.lifecycle.types import PromptRenderInput, PromptRenderResult
from agent.prompting.listening_block import HeardLine
from conversation.context_scope import history_filter
from session.maintenance_progress import MaintenanceProgress, window_key
from .compaction import with_working_summary
from .helpers import (
    build_turn_injection_prompt,
    get_session_metadata,
    get_window_preloaded_tools,
    get_window_sources,
)

if TYPE_CHECKING:
    from agent.tools.registry import ToolRegistry
    from conversation.context_scope import ContextView
    from session.manager import SessionManager
    from session.manager.window import WindowPreparation


@dataclass
class CompactionRenderer:
    """One execution's immutable input and dependencies for candidate prompt rendering."""

    sessions: SessionManager
    view: ContextView | None
    message_limit: int
    input: PromptRenderInput
    current_message: dict
    render_prompt: Callable[[PromptRenderInput], Awaitable[PromptRenderResult]]
    tools: ToolRegistry
    search_enabled: bool
    disabled_tools: set[str]
    external_restricted: bool
    heard: Callable[[], list[HeardLine]]

    def _snapshot(self, prepared: WindowPreparation):
        stored = self.sessions.window_snapshot(
            prepared.session_key, self.view, message_limit=self.message_limit
        )
        progress = MaintenanceProgress.load(
            self.sessions.maintenance_progress(stored).dump()
        )
        progress.windows[window_key(self.view)] = prepared.stop
        return replace(
            stored,
            messages=stored.messages[: self.message_limit],
            maintenance_progress=progress,
        )

    def history_tools(self, prepared: WindowPreparation) -> list[str]:
        """Only tools belonging to the candidate original window remain preloaded."""
        return get_window_preloaded_tools(
            self._snapshot(prepared), 500, self.view, self.tools
        )

    async def render(
        self, prepared: WindowPreparation, summary: str, visible_tools: list[str]
    ) -> list[dict]:
        """Re-render dynamic context while protecting current input and attachments."""
        snapshot = self._snapshot(prepared)
        history = snapshot.get_history(
            start_index=prepared.stop, include=history_filter(self.view)
        )
        sources = get_window_sources(snapshot, 500, self.view, self.heard())
        injection = build_turn_injection_prompt(
            tools=self.tools,
            tool_search_enabled=self.search_enabled,
            visible_names=(
                set(visible_tools) | self.disabled_tools
                if self.search_enabled
                else None
            ),
            external_only=self.external_restricted,
        )
        candidate = await self.render_prompt(
            replace(
                self.input,
                history=history,
                session_metadata=get_session_metadata(snapshot),
                window_sources=sources,
                turn_injection_prompt=injection,
            )
        )
        if self.current_message.get("role") == "user":
            candidate.messages[-1] = deepcopy(self.current_message)
        return with_working_summary(candidate.messages, summary)
