from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, TypeAlias, cast

from agent.core.passive_support import build_context_hint_message
from agent.core.types import ContextRequest
from agent.lifecycle.phase import PhaseFrame, PhaseModule, topo_sort_modules
from agent.core.turn_events import TurnEvents, read_only
from agent.lifecycle.types import (
    PromptRenderCtx,
    PromptRenderInput,
    PromptRenderResult,
)
from prompts.natural_chat import NATURAL_CHAT_PROMPT
from shiori_sdk.core.conversation import PromptRendering, ReplyMode
from shiori_sdk.prompting import PromptSectionRender

if TYPE_CHECKING:
    from agent.context import ContextBuilder


@dataclass
class PromptRenderFrame(PhaseFrame[PromptRenderInput, PromptRenderResult]):
    pass


PromptRenderModules: TypeAlias = list[PhaseModule[PromptRenderFrame]]


_CTX_SLOT = "prompt:ctx"
_RESULT_SLOT = "prompt:result"
_REPLY_MODE_SLOT = "prompt:reply_mode"


class _BuildPromptRenderCtxModule:
    slot = "prompt_render.build_ctx"
    requires: tuple[str, ...] = ()
    produces = (_CTX_SLOT,)

    async def run(self, frame: PromptRenderFrame) -> PromptRenderFrame:
        input = frame.input
        frame.slots[_CTX_SLOT] = PromptRenderCtx(
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
        return frame


class _EmitPromptRenderCtxModule:
    slot = "prompt_render.emit"
    requires = ("prompt_render.build_ctx", _CTX_SLOT)
    produces = (_CTX_SLOT,)

    def __init__(self, events: TurnEvents) -> None:
        self._events = events

    async def run(self, frame: PromptRenderFrame) -> PromptRenderFrame:
        ctx = cast(PromptRenderCtx, frame.slots[_CTX_SLOT])

        def apply(event: PromptRendering) -> None:
            ctx.system_sections_top[:] = event.system_sections_top
            ctx.system_sections_bottom[:] = event.system_sections_bottom
            ctx.extra_hints[:] = event.extra_hints
            frame.slots[_REPLY_MODE_SLOT] = _rendered_reply_mode(event, frame.input)

        await self._events.emit(_prompt_rendering(ctx, frame.input), apply)
        return frame


def _prompt_rendering(
    ctx: PromptRenderCtx, input: PromptRenderInput
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
        reply_mode=_role_reply_mode(input),
    )


def _role_reply_mode(input: PromptRenderInput) -> ReplyMode:
    """The role's natural-chat switch, the initial ``PromptRendering.reply_mode``."""
    runtime_config = input.session_metadata.get("role_runtime_config") or {}
    enabled = runtime_config.get("natural_chat_enabled") is True
    return "sequence" if enabled else "single"


def _rendered_reply_mode(event: PromptRendering, input: PromptRenderInput) -> ReplyMode:
    """The final reply mode, a sequence only where the request allows one."""
    allowed = input.supports_reply_sequence and not input.minimal_request
    return event.reply_mode if allowed else "single"


class _RenderPromptModule:
    slot = "prompt_render.render"
    requires = ("prompt_render.emit", _CTX_SLOT)
    produces = (_RESULT_SLOT,)

    def __init__(self, context: ContextBuilder) -> None:
        self._context = context

    async def run(self, frame: PromptRenderFrame) -> PromptRenderFrame:
        ctx = cast(PromptRenderCtx, frame.slots[_CTX_SLOT])
        minimal = frame.input.minimal_request
        natural_chat = frame.slots[_REPLY_MODE_SLOT] == "sequence"
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
                message_source=frame.input.message_source,
                retrieved_memory_block=ctx.retrieved_memory_block,
                disabled_sections=ctx.disabled_sections,
                turn_injection_prompt=ctx.turn_injection_prompt,
                context_scope=frame.input.context_scope,
                thread_id=frame.input.thread_id,
                window_sources=frame.input.window_sources,
                minimal_request=minimal,
                text_attachment_tool=frame.input.text_attachment_tool,
            ),
            system_sections_top=[] if minimal else ctx.system_sections_top,
            system_sections_bottom=[] if minimal else bottom_sections,
            session_metadata=ctx.session_metadata,
        )
        messages = list(rendered.messages)
        current_message = messages[-1] if frame.input.include_current_message else None
        if not frame.input.include_current_message:
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
        frame.slots[_RESULT_SLOT] = PromptRenderResult(
            messages=messages,
            current_message=current_message,
            natural_chat=natural_chat,
        )
        return frame


class _ReturnPromptRenderResultModule:
    slot = "prompt_render.return"
    requires = ("prompt_render.render", _RESULT_SLOT)

    async def run(self, frame: PromptRenderFrame) -> PromptRenderFrame:
        frame.output = cast(PromptRenderResult, frame.slots[_RESULT_SLOT])
        return frame


def default_prompt_render_modules(
    events: TurnEvents, context: ContextBuilder
) -> PromptRenderModules:
    builtins: PromptRenderModules = [
        _BuildPromptRenderCtxModule(),
        _EmitPromptRenderCtxModule(events),
        _RenderPromptModule(context),
        _ReturnPromptRenderResultModule(),
    ]
    return cast(PromptRenderModules, topo_sort_modules(builtins))
