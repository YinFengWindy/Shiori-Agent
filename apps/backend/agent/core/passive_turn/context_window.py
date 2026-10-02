"""Budget inspection and manual compaction, without executing a conversation turn."""

from dataclasses import asdict
from typing import Awaitable, Callable

from agent.lifecycle.types import PromptRenderInput, PromptRenderResult
from agent.looping.ports import LLMConfig
from agent.prompting.usage_anchor import turn_usage_context
from agent.provider import LLMProvider
from agent.tools.registry import ToolRegistry
from bus.events import InboundMessage
from conversation.context_scope import ContextView
from core.compaction import (
    CompactionController,
    CompactionFailedError,
    CompactionPolicy,
    NO_COMPLETE_TURNS,
)
from core.compaction_feedback import compaction_feedback
from session.manager import Session, SessionManager
from session.maintenance_progress import window_key
from session.manager.models import consolidation_cursor
from .context_window_request import prepare_context_window_request


class ContextWindow:
    """Own the minimal idle-context contract consumed by commands and the composer."""

    def __init__(
        self,
        sessions: SessionManager,
        controller: CompactionController,
        provider: LLMProvider,
        config: LLMConfig,
        tools: ToolRegistry,
        render_prompt: Callable[[PromptRenderInput], Awaitable[PromptRenderResult]],
    ) -> None:
        self.sessions = sessions
        self.controller = controller
        self.provider = provider
        self.config = config
        self.tools = tools
        self.render_prompt = render_prompt

    @turn_usage_context
    async def inspect(
        self,
        *,
        session: Session,
        context_view: ContextView | None,
        msg: InboundMessage,
        compact: bool = False,
    ) -> dict:
        """Measure the complete persisted request and optionally force the controller."""
        policy = CompactionPolicy(self.config.compaction_retained_turns)
        request = await prepare_context_window_request(
            sessions=self.sessions,
            session_key=session.key,
            view=context_view,
            msg=msg,
            provider=self.provider,
            model=self.config.model,
            max_tokens=self.config.max_tokens,
            tools=self.tools,
            search_enabled=self.config.tool_search_enabled,
            render_prompt=self.render_prompt,
        )
        before = request.measure(request.messages)
        limit = request.renderer.message_limit
        prepared = await self.sessions.prepare_window(
            session.key,
            context_view,
            # The same bound as the controller's configured candidate.
            keep_turns=min(policy.retained_turns, limit),
            message_limit=limit,
        )
        progress = self.sessions.maintenance_progress(session)
        state = {
            "session_key": session.key,
            "context_key": window_key(context_view),
            "model": self.provider.context_model(self.config.model),
            "model_identity": self.provider.context_identity(self.config.model),
            "tokens": before.estimate.tokens,
            "source": before.estimate.source,
            "model_context_window": before.model_context_window,
            "input_limit_tokens": before.input_limit_tokens,
            "budget": asdict(before),
            "configured_retained_turns": policy.retained_turns,
            "window_start": progress.cursor(context_view),
            "compaction_count": progress.compaction_counts.get(
                window_key(context_view), 0
            ),
            "window_version": progress.window_versions.get(window_key(context_view), 0),
            "memory_cursor": consolidation_cursor(
                session, context_view.scope if context_view else None
            ),
            "memory_version": progress.memory_version,
            "published_version": progress.published_version,
            "relationship_version": progress.relationship_version,
            "memory_status": (
                "consumer_failed"
                if progress.consumer_error
                else ("pending_consumers" if progress.pending_consumers else "covered")
            ),
            "last_compaction": self.controller.latest(session.key, context_view),
            "last_request": self.controller.latest(
                session.key, context_view, request=True
            ),
            "can_compact": prepared is not None,
            "busy": False,
            "reason": "" if prepared else NO_COMPLETE_TURNS,
            "result": None,
        }
        if not compact or prepared is None:
            return state
        failure: BaseException | None = None
        try:
            _, result = await self.controller.ensure(
                session_key=session.key,
                view=context_view,
                policy=policy,
                message_limit=limit,
                budget=before,
                render=request.render,
                measure=request.measure,
                reason="manual",
            )
        except CompactionFailedError as error:
            result = error.result
            failure = error.__cause__ or error
        # Memory can commit even when the window fails. Re-read both owners,
        # and re-render the persisted request rather than exposing a rejected draft.
        state = await self.inspect(session=session, context_view=context_view, msg=msg)
        state["result"] = compaction_feedback(result, failure)
        state["reason"] = state["result"]["error"]
        return state
