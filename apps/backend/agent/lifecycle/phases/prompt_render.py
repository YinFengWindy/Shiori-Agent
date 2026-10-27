from __future__ import annotations

from typing import TYPE_CHECKING

from agent.core.passive_support import build_context_hint_message
from agent.core.types import ContextRequest
from agent.core.turn_events import TurnEvents, read_only
from agent.lifecycle.types import (
    PromptRenderCtx,
    PromptRenderInput,
    PromptRenderResult,
)
from core.roles.natural_chat import natural_chat_enabled
from core.roles.store import RoleStore
from prompts.natural_chat import NATURAL_CHAT_PROMPT
from shiori_sdk.core.conversation import PromptRendering, ReplyMode
from shiori_sdk.prompting import PromptSectionRender

if TYPE_CHECKING:
    from agent.context import ContextBuilder


class PromptRenderPhase:
    """Renders one request's prompt after ``PromptRendering`` has run."""

    def __init__(self, events: TurnEvents, context: ContextBuilder) -> None:
        self._events = events
        self._context = context

    async def run(self, input: PromptRenderInput) -> PromptRenderResult:
        """Emits ``PromptRendering``, then renders the request with its result."""
        ctx = _prompt_render_ctx(input)
        reply_mode = await self._emit(ctx, input)
        return self._render(ctx, input, natural_chat=reply_mode == "sequence")

    async def _emit(self, ctx: PromptRenderCtx, input: PromptRenderInput) -> ReplyMode:
        """Emits ``PromptRendering``, writes it back to ``ctx``, returns the reply mode.

        The event cannot be vetoed (a veto fails the turn), so ``apply`` always
        runs before the emit returns.
        """
        reply_mode: ReplyMode | None = None

        def apply(event: PromptRendering) -> None:
            nonlocal reply_mode
            ctx.system_sections_top[:] = event.system_sections_top
            ctx.system_sections_bottom[:] = event.system_sections_bottom
            ctx.extra_hints[:] = event.extra_hints
            reply_mode = _rendered_reply_mode(event, input)

        await self._events.emit(
            _prompt_rendering(ctx, input, self._context.runtime_roles), apply
        )
        if reply_mode is None:
            raise RuntimeError("PromptRendering 发出后未写回最终事件")
        return reply_mode

    def _render(
        self, ctx: PromptRenderCtx, input: PromptRenderInput, *, natural_chat: bool
    ) -> PromptRenderResult:
        minimal = input.minimal_request
        bottom_sections = list(ctx.system_sections_bottom)
        if natural_chat:
            bottom_sections.append(
                PromptSectionRender(
                    name="natural_chat", content=NATURAL_CHAT_PROMPT, is_static=False
                )
            )
        rendered = self._context.render(
            ContextRequest(
                history=[] if minimal else ctx.history,
                current_message=ctx.content,
                media=ctx.media,
                skill_names=ctx.skill_names,
                channel=ctx.channel,
                chat_id=ctx.chat_id,
                message_timestamp=ctx.timestamp,
                message_source=input.message_source,
                retrieved_memory_block=ctx.retrieved_memory_block,
                disabled_sections=ctx.disabled_sections,
                turn_injection_prompt=ctx.turn_injection_prompt,
                context_scope=input.context_scope,
                thread_id=input.thread_id,
                window_sources=input.window_sources,
                minimal_request=minimal,
                text_attachment_tool=input.text_attachment_tool,
            ),
            system_sections_top=[] if minimal else ctx.system_sections_top,
            system_sections_bottom=[] if minimal else bottom_sections,
            session_metadata=ctx.session_metadata,
        )
        messages = list(rendered.messages)
        current_message = messages[-1] if input.include_current_message else None
        if not input.include_current_message:
            # The envelope owner always appends the current input last. Idle
            # inspection keeps every persisted row and context frame, but no draft.
            messages.pop()
        if ctx.extra_hints and not minimal:
            messages.append(
                build_context_hint_message(
                    "plugin_hints",
                    "\n".join(ctx.extra_hints),
                )
            )
        return PromptRenderResult(
            messages=messages,
            current_message=current_message,
            natural_chat=natural_chat,
        )


def _prompt_render_ctx(input: PromptRenderInput) -> PromptRenderCtx:
    """The request's prompt context, before ``PromptRendering`` writes to it."""
    return PromptRenderCtx(
        session_key=input.session_key,
        channel=input.channel,
        chat_id=input.chat_id,
        content=input.content,
        media=input.media,
        timestamp=input.timestamp,
        history=input.history,
        skill_names=input.skill_names,
        retrieved_memory_block=input.retrieved_memory_block,
        disabled_sections=set(input.disabled_sections),
        turn_injection_prompt=input.turn_injection_prompt,
        session_metadata=dict(input.session_metadata),
        extra_hints=list(input.extra_hints or []),
    )


def _prompt_rendering(
    ctx: PromptRenderCtx, input: PromptRenderInput, roles: RoleStore
) -> PromptRendering:
    """The ``PromptRendering`` projection of the request's prompt context."""
    return PromptRendering(
        session_key=ctx.session_key,
        channel=ctx.channel,
        chat_id=ctx.chat_id,
        content=ctx.content,
        media=tuple(ctx.media or ()),
        timestamp=ctx.timestamp,
        context_scope=input.context_scope,
        history=tuple(read_only(message) for message in ctx.history),
        skill_names=tuple(ctx.skill_names or ()),
        retrieved_memory_block=ctx.retrieved_memory_block,
        disabled_sections=frozenset(ctx.disabled_sections),
        turn_injection_prompt=ctx.turn_injection_prompt,
        session_metadata=read_only(ctx.session_metadata),
        supports_reply_sequence=input.supports_reply_sequence,
        minimal_request=input.minimal_request,
        system_sections_top=tuple(ctx.system_sections_top),
        system_sections_bottom=tuple(ctx.system_sections_bottom),
        extra_hints=tuple(ctx.extra_hints),
        reply_mode=_role_reply_mode(roles, input),
    )


def _role_reply_mode(roles: RoleStore, input: PromptRenderInput) -> ReplyMode:
    """The role record's switch, the initial ``PromptRendering.reply_mode``.

    ``session_metadata["role_runtime_config"]`` is a copy and is not read.
    """
    role_id = str(input.session_metadata.get("role_id") or "").strip()
    role = roles.get_role(role_id) if role_id else None
    return "sequence" if natural_chat_enabled(role) else "single"


def _rendered_reply_mode(event: PromptRendering, input: PromptRenderInput) -> ReplyMode:
    """The final reply mode, a sequence only where the request allows one."""
    allowed = input.supports_reply_sequence and not input.minimal_request
    return event.reply_mode if allowed else "single"
