"""Idle model-window requests rendered by the same owner as speaking turns."""

from dataclasses import dataclass
from typing import Awaitable, Callable

from agent.lifecycle.types import (
    PromptRenderInput,
    PromptRenderResult,
    inbound_thread_id,
)
from agent.prompting.listening_block import turn_heard
from agent.provider import LLMProvider
from agent.tools.external_access import external_tools_restricted
from agent.tools.registry import ToolRegistry
from bus.events import InboundMessage
from conversation.context_scope import ContextView
from core.common.message_source import MessageSource
from session.manager import SessionManager
from session.manager.window import WindowPreparation
from session.maintenance_progress import window_key
from .compaction_render import CompactionRenderer
from .helpers import get_window_preloaded_tools


@dataclass
class ContextWindowRequest:
    """Capture one immutable model, persisted prefix, and candidate renderer."""

    renderer: CompactionRenderer
    provider: LLMProvider
    model: str
    max_tokens: int
    schemas: list[dict]
    messages: list[dict]

    def measure(self, messages: list[dict]):
        """Use provider normalization and shared usage anchors without a model call."""
        budget = self.provider.input_budget(
            messages=messages,
            tools=self.schemas,
            model=self.model,
            max_tokens=self.max_tokens,
        )
        if budget is None:
            raise ValueError("模型档案缺少上下文容量")
        return budget

    async def render(self, prepared: WindowPreparation, summary: str):
        """Drop only tools owned by removed history before checking the candidate."""
        self.schemas = self.renderer.tool_schemas(self.renderer.history_tools(prepared))
        return await self.renderer.render(
            prepared, summary, [s["function"]["name"] for s in self.schemas]
        )


async def prepare_context_window_request(
    *,
    sessions: SessionManager,
    session_key: str,
    view: ContextView | None,
    msg: InboundMessage,
    provider: LLMProvider,
    model: str,
    max_tokens: int,
    tools: ToolRegistry,
    search_enabled: bool,
    render_prompt: Callable[[PromptRenderInput], Awaitable[PromptRenderResult]],
) -> ContextWindowRequest:
    """Assemble persisted context with no synthetic user message or draft retrieval.

    Read-only: the window is model independent, so measuring under any model
    (including a vision model) never writes session state.
    """
    limit = len(sessions.get_or_create(session_key).messages)
    snapshot = sessions.window_snapshot(session_key, view, message_limit=limit)
    progress = sessions.maintenance_progress(snapshot)
    source = MessageSource.from_inbound(msg)
    renderer = CompactionRenderer(
        sessions,
        view,
        limit,
        PromptRenderInput(
            session_key=session_key,
            channel=msg.channel,
            chat_id=msg.chat_id,
            content="",
            media=None,
            timestamp=msg.timestamp,
            history=[],
            skill_names=None,
            retrieved_memory_block="",
            disabled_sections=set(),
            turn_injection_prompt="",
            message_source=source,
            context_scope=view.scope if view else None,
            thread_id=inbound_thread_id(msg),
            include_current_message=False,
        ),
        None,
        render_prompt,
        tools,
        search_enabled,
        set(),
        external_tools_restricted(view, source),
        lambda: turn_heard(sessions, view),
    )
    request = ContextWindowRequest(renderer, provider, model, max_tokens, [], [])
    request.schemas = renderer.tool_schemas(
        get_window_preloaded_tools(snapshot, 500, view, tools)
    )
    request.messages = await renderer.render_snapshot(
        snapshot,
        progress.cursor(view),
        progress.summaries.get(window_key(view), ""),
        [schema["function"]["name"] for schema in request.schemas],
    )
    # A role/identity change or undo while rendering invalidates this entire read.
    sessions.window_snapshot(session_key, view, message_limit=limit, expected=progress)
    return request
