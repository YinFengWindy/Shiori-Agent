"""The core modules that provide their services to the plugin kernel (#901 P2).

Each entry publishes one core module's keys before any plugin is planned. A
core module whose provide raises aborts startup (§8.5); plugins only ever fail
on their own.
"""

from __future__ import annotations

from agent.config import resolve_config_reference
from agent.plugin_host.core_keys import (
    HOST_CONFIG_REFERENCES,
    HOST_DIAGNOSTICS,
    CoreModule,
    CoreProvide,
)
from core.common.diagnostics import PluginDiagnosticsBinder
from core.common.global_hook_stack import ProcessCrashReporting
from shiori_sdk.core.crash_reporting import CRASH_REPORTING


def provide_diagnostics(provide: CoreProvide) -> None:
    """``CRASH_REPORTING`` and the ``diagnostics`` capability built over it (D13b)."""
    crash_reporting = ProcessCrashReporting()
    provide(CRASH_REPORTING, crash_reporting)
    provide(HOST_DIAGNOSTICS, PluginDiagnosticsBinder(crash_reporting))


def provide_config_references(provide: CoreProvide) -> None:
    """The host's ``${NAME}`` expansion behind ``config.resolve_reference``."""
    provide(HOST_CONFIG_REFERENCES, resolve_config_reference)


def plugin_core_modules() -> tuple[CoreModule, ...]:
    """The core provide list, in provide order, for one runtime generation."""
    return (provide_diagnostics, provide_config_references)
