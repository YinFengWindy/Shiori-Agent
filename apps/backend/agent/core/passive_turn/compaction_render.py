"""Render a candidate persisted window with fresh sources and the exact current input."""

from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Awaitable, Callable, TYPE_CHECKING

from agent.context import without_attachment_tool_hints
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
    turn_tool_names,
)
from .tool_visibility import initial_tool_order
from .minimal_request import replace_current_input

if TYPE_CHECKING:
    from agent.tools.registry import ToolRegistry
    from conversation.context_scope import ContextView
    from session.manager import Session, SessionManager
    from session.manager.window import WindowPreparation


@dataclass
class CompactionRenderer:
    """One execution's immutable input and dependencies for candidate prompt rendering."""

    sessions: SessionManager
    view: ContextView | None
    message_limit: int
    input: PromptRenderInput
    current_message: dict | None
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

    def tool_schemas(self, history: list[str]):
        """Resolve initial schemas using this renderer's tool visibility policy."""
        names = (
            initial_tool_order(
                self.tools,
                history,
                disabled=self.disabled_tools,
                external_restricted=self.external_restricted,
            )
            if self.search_enabled
            else turn_tool_names(
                self.tools,
                None,
                disabled=self.disabled_tools,
                external_restricted=self.external_restricted,
            )
        )
        return self.tools.get_schemas(
            names=names, external_only=self.external_restricted
        )

    async def render(
        self, prepared: WindowPreparation, summary: str, visible_tools: list[str]
    ) -> list[dict]:
        """Re-render dynamic context while protecting current input and attachments."""
        snapshot = self._snapshot(prepared)
        return await self.render_snapshot(
            snapshot, prepared.stop, summary, visible_tools
        )

    async def render_snapshot(
        self, snapshot: Session, start: int, summary: str, visible_tools: list[str]
    ) -> list[dict]:
        """Render both the current and candidate windows through the prompt owner."""
        history = snapshot.get_history(
            start_index=start, include=history_filter(self.view)
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
        if (
            self.current_message is not None
            and self.current_message.get("role") == "user"
        ):
            replace_current_input(
                candidate.messages, self.current_message, candidate.current_message
            )
        return with_working_summary(candidate.messages, summary)

    async def render_minimal(self, summary: str) -> list[dict]:
        """Render essential constraints with this execution's exact input and owner."""
        candidate = await self.render_prompt(
            replace(
                self.input,
                history=[],
                retrieved_memory_block="",
                skill_names=[],
                turn_injection_prompt="",
                extra_hints=[],
                window_sources=(),
                minimal_request=True,
            )
        )
        if self.current_message is not None:
            # Tools are disabled here, so drop instructions to call read_file.
            replace_current_input(
                candidate.messages,
                without_attachment_tool_hints(self.current_message),
                candidate.current_message,
            )
        return with_working_summary(candidate.messages, summary)
