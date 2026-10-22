"""The core modules that provide their services to the plugin kernel (#901 P2).

Each entry publishes one core module's keys before any plugin is planned. A
core module whose provide raises aborts startup (§8.5); plugins only ever fail
on their own. Adapters that turn a core service into a v2 capability live
here, since bootstrap already imports both the core and the assembly layer.
"""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path

from agent.config import resolve_config_reference
from agent.plugin_host.core_keys import (
    HOST_CONFIG_REFERENCES,
    HOST_DIAGNOSTICS,
    HOST_TOOL_HOOKS,
    HOST_TOOL_TURN,
    HOST_TOOLS,
    CoreModule,
    CoreProvide,
)
from agent.tool_hooks.plugin_capability import PluginToolHooks
from agent.tools.plugin_capability import PluginTools
from agent.tools.registry import ToolRegistry
from agent.tools.turn_scope import current_tool_turn
from core.common.diagnostics import HostDiagnostics
from core.common.global_hook_stack import ProcessCrashReporting
from shiori_sdk.core.crash_reporting import CRASH_REPORTING


def plugin_core_modules(
    plugin_dirs: Sequence[Path], *, tools: ToolRegistry | None
) -> tuple[CoreModule, ...]:
    """The core provide list, in provide order, for one runtime generation.

    ``plugin_dirs`` are the generation's plugin discovery roots: every plugin
    is a directory directly under one, which is how diagnostics attributes a
    traceback frame to ``plugins/<directory>/...``. ``tools`` is the
    generation's tool registry; without one (host tests) a plugin declaring
    ``tools`` fails before setup.
    """
    roots = [("plugins", directory.resolve()) for directory in plugin_dirs]

    def provide_diagnostics(provide: CoreProvide) -> None:
        """``CRASH_REPORTING`` and the ``diagnostics`` capability over it (D13b)."""
        crash_reporting = ProcessCrashReporting()
        provide(CRASH_REPORTING, crash_reporting)
        provide(HOST_DIAGNOSTICS, HostDiagnostics(crash_reporting, roots))

    def provide_config_references(provide: CoreProvide) -> None:
        """The host's ``${NAME}`` expansion behind ``config.resolve_reference``."""
        provide(HOST_CONFIG_REFERENCES, resolve_config_reference)

    def provide_tools(provide: CoreProvide) -> None:
        """Plugin tools, tool hooks and the current tool turn (``agent.tools``)."""
        if tools is not None:
            provide(HOST_TOOLS, PluginTools(tools))
        provide(HOST_TOOL_HOOKS, PluginToolHooks())
        provide(HOST_TOOL_TURN, current_tool_turn)

    return (provide_diagnostics, provide_config_references, provide_tools)
