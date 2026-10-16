"""Fixed plugin contributions for host tests that need no real plugin kernel."""

from collections.abc import Sequence
from dataclasses import dataclass

from agent.tool_hooks.base import ToolHook


@dataclass
class StaticPluginContributions:
    """A ``PluginContributionSource`` whose contributions never change."""

    before_turn_modules: Sequence[object] = ()
    before_reasoning_modules: Sequence[object] = ()
    prompt_render_modules: Sequence[object] = ()
    before_step_modules: Sequence[object] = ()
    after_step_modules: Sequence[object] = ()
    after_reasoning_modules: Sequence[object] = ()
    after_turn_modules: Sequence[object] = ()
    tool_hooks: Sequence[ToolHook] = ()
