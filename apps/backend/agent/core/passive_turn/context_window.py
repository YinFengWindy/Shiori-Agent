"""Budget inspection and manual compaction, without executing a conversation turn."""

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
)
from core.compaction_feedback import compaction_feedback
from session.manager import Session, SessionManager
from session.maintenance_progress import window_key
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
            session.key, context_view, keep_turns=0, message_limit=limit
        )
        state = {
            "session_key": session.key,
            "context_key": window_key(context_view),
            "model": self.provider.context_model(self.config.model),
            "model_identity": self.provider.context_identity(self.config.model),
            "tokens": before.estimate.tokens,
            "source": before.estimate.source,
            "context_window_tokens": before.context_window_tokens,
            "input_limit_tokens": before.input_limit_tokens,
            "can_compact": prepared is not None,
            "busy": False,
            "reason": "" if prepared else "没有可压缩的完整轮次",
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
        state["result"] = compaction_feedback(result, failure)
        state["reason"] = state["result"]["error"]
        if result.committed:
            state["tokens"] = result.after_tokens
            state["source"] = result.after_source
            state["can_compact"] = (
                await self.sessions.prepare_window(
                    session.key, context_view, keep_turns=0, message_limit=limit
                )
                is not None
            )
        return state
