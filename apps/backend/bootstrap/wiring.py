from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, Any, Callable, Mapping

from agent.context import ContextBuilder
from agent.lifecycle.facade import TurnLifecycle
from shiori_sdk.tools import Tool
from bootstrap.toolsets.mcp import McpToolsetProvider
from bootstrap.toolsets.memory import MemoryToolsetProvider
from bootstrap.toolsets.meta import CommonMetaToolsetProvider, SpawnToolsetProvider
from bootstrap.toolsets.protocol import ToolsetProvider
from bootstrap.toolsets.schedule import SchedulerToolsetProvider
from core.roles import RoleStore

if TYPE_CHECKING:
    from agent.looping.interrupt import TurnInterruptState


# (workspace, memory store, the runtime's shared role store) -> context builder.
ContextFactory = Callable[[Path, Any, RoleStore], Any]
ToolsetProviderFactory = Callable[[], ToolsetProvider]

_MEMORY_WIRING: dict[str, ToolsetProviderFactory] = {
    "default": MemoryToolsetProvider,
}
_CONTEXT_WIRING: dict[str, ContextFactory] = {
    "default": lambda workspace, memory, roles: ContextBuilder(
        workspace, memory=memory, runtime_roles=roles
    ),
}
_TOOLSET_WIRING: dict[str, ToolsetProviderFactory] = {
    "spawn": SpawnToolsetProvider,
    "schedule": SchedulerToolsetProvider,
    "mcp": McpToolsetProvider,
}


def wire_turn_lifecycle(
    lifecycle: TurnLifecycle,
    *,
    active_turn_states: Mapping[str, "TurnInterruptState"],
) -> None:
    from agent.looping.interrupt import tracked_turn_state
    from shiori_sdk.core.conversation import StepFinished
    from agent.turns.reply_sequence import presented_tool_chain, reply_is_buffered

    async def _progress_reporter(ctx: StepFinished) -> None:
        state = tracked_turn_state(active_turn_states, ctx.session_key)
        if state is None:
            return
        if ctx.partial_reply and not reply_is_buffered():
            state.partial_reply = ctx.partial_reply
        if ctx.partial_thinking:
            state.partial_thinking = ctx.partial_thinking
        state.tools_used = list(ctx.tools_used_so_far)
        state.tool_chain_partial = presented_tool_chain(
            ctx.tool_chain_partial, buffered=reply_is_buffered()
        )

    lifecycle.on_step_finished(_progress_reporter)


def resolve_memory_toolset_provider(name: str) -> ToolsetProvider:
    if name not in _MEMORY_WIRING:
        choices = ", ".join(sorted(_MEMORY_WIRING))
        raise ValueError(f"未知 memory wiring: {name}；可选值: {choices}")
    return _MEMORY_WIRING[name]()


def resolve_context_factory(name: str) -> ContextFactory:
    if name not in _CONTEXT_WIRING:
        choices = ", ".join(sorted(_CONTEXT_WIRING))
        raise ValueError(f"未知 context wiring: {name}；可选值: {choices}")
    return _CONTEXT_WIRING[name]


def resolve_toolset_provider(
    name: str, *, readonly_tools: dict[str, Tool] | None = None
) -> ToolsetProvider:
    if name == "meta_common":
        return CommonMetaToolsetProvider(readonly_tools or {})
    if name not in _TOOLSET_WIRING:
        choices = ", ".join(sorted(["meta_common", *_TOOLSET_WIRING.keys()]))
        raise ValueError(f"未知 toolset wiring: {name}；可选值: {choices}")
    return _TOOLSET_WIRING[name]()
