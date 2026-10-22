"""Shiori plugin kernel: keys, typed events, ordered setup, scoped disposal, reload.

The kernel knows no business: it imports nothing outside this package (an
import-linter contract keeps it so). Hosts and the test harness run the same
code (D3).
"""

from .contracts import (
    FailurePolicy,
    Key,
    KernelError,
    PluginFailed,
    PluginSpec,
    PluginStarted,
    PluginStopped,
    Veto,
    failure_policy,
)
from .diagnostics import PackageContractError, PluginDiagnostic, RendererActivationError
from .kernel import CORE, DRAIN_TIMEOUT, Context, Kernel, PluginStatus
from .scope import Scope

__all__ = [
    "CORE",
    "Context",
    "DRAIN_TIMEOUT",
    "FailurePolicy",
    "Kernel",
    "KernelError",
    "Key",
    "PackageContractError",
    "PluginDiagnostic",
    "PluginFailed",
    "PluginSpec",
    "PluginStarted",
    "PluginStatus",
    "PluginStopped",
    "RendererActivationError",
    "Scope",
    "Veto",
    "failure_policy",
]
