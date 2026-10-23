"""Human-readable lifecycle inspection, separate from runtime construction."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, cast

from agent.turns.outbound import BusOutboundPort

if TYPE_CHECKING:
    from bootstrap.tools import CoreRuntime


async def inspect_core_modules(core: "CoreRuntime") -> str:
    """Renders the lifecycle modules configured for one runtime generation."""
    if core.plugin_manager is not None:
        await core.plugin_manager.load_all()

    from agent.core.turn_events import TurnEvents, core_kernel
    from agent.lifecycle.phase import inspect_phase
    from agent.lifecycle.phases.after_reasoning import (
        default_after_reasoning_modules,
    )
    from agent.lifecycle.phases.after_step import default_after_step_modules
    from agent.lifecycle.phases.after_turn import default_after_turn_modules
    from agent.lifecycle.phases.before_reasoning import (
        default_before_reasoning_modules,
    )
    from agent.lifecycle.phases.before_step import default_before_step_modules
    from agent.lifecycle.phases.before_turn import default_before_turn_modules
    from agent.lifecycle.phases.prompt_render import default_prompt_render_modules

    manager = core.plugin_manager
    # Only the modules are listed; nothing is emitted through these events.
    events = TurnEvents(core.event_bus, core_kernel)
    before_turn_modules = manager.before_turn_modules if manager is not None else []
    before_reasoning_modules = (
        manager.before_reasoning_modules if manager is not None else []
    )
    prompt_render_modules = manager.prompt_render_modules if manager is not None else []
    before_step_modules = manager.before_step_modules if manager is not None else []
    after_step_modules = manager.after_step_modules if manager is not None else []
    after_reasoning_modules = (
        manager.after_reasoning_modules if manager is not None else []
    )
    after_turn_modules = manager.after_turn_modules if manager is not None else []

    agent_core = cast(Any, getattr(core.loop, "_agent_core"))
    pipeline = agent_core.pipeline
    reasoner = getattr(core.loop, "_reasoner", None)
    context = getattr(reasoner, "_context", None)

    phases = [
        (
            "before_turn",
            default_before_turn_modules(
                core.event_bus,
                events,
                core.session_manager,
                cast(Any, getattr(pipeline, "_context_store", None)),
                plugin_modules=cast(Any, before_turn_modules),
            ),
        ),
        (
            "before_reasoning",
            default_before_reasoning_modules(
                core.event_bus,
                events,
                core.tools,
                core.session_manager,
                cast(Any, context),
                plugin_modules=cast(Any, before_reasoning_modules),
            ),
        ),
        (
            "prompt_render",
            default_prompt_render_modules(
                core.event_bus,
                events,
                cast(Any, context),
                plugin_modules=cast(Any, prompt_render_modules),
            ),
        ),
        (
            "before_step",
            default_before_step_modules(
                core.event_bus,
                events,
                plugin_modules=cast(Any, before_step_modules),
            ),
        ),
        (
            "after_step",
            default_after_step_modules(
                core.event_bus,
                events,
                plugin_modules=cast(Any, after_step_modules),
            ),
        ),
        (
            "after_reasoning",
            default_after_reasoning_modules(
                core.event_bus,
                events,
                cast(Any, getattr(pipeline, "_session", None)),
                plugin_modules=cast(Any, after_reasoning_modules),
            ),
        ),
        (
            "after_turn",
            default_after_turn_modules(
                core.event_bus,
                events,
                cast(
                    Any, getattr(pipeline, "_outbound_port", BusOutboundPort(core.bus))
                ),
                cast(Any, context),
                cast(int, getattr(pipeline, "_history_window", 500)),
                plugin_modules=cast(Any, after_turn_modules),
            ),
        ),
    ]

    parts: list[str] = []
    for phase_name, modules in phases:
        parts.append("=" * 60)
        parts.append(phase_name)
        parts.append("=" * 60)
        parts.append(inspect_phase(modules))
    return "\n".join(parts)
