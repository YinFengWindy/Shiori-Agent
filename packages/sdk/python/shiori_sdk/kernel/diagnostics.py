"""Serializable plugin failure data shared by package validation, the kernel and hosts."""

from __future__ import annotations

from dataclasses import asdict, dataclass


@dataclass(frozen=True)
class PluginDiagnostic:
    """Stable host-facing failure details; ``reason`` preserves the original cause.

    ``stage`` names where the failure happened (``validation``, ``discovery``,
    ``trust``, ``dependency``, ``setup``, ``reload`` or a renderer entry kind)
    and ``state`` the lifecycle state the plugin is left in.
    """

    code: str
    stage: str
    field: str
    reason: str
    path: str = ""
    state: str = "BLOCKED"

    def to_dict(self) -> dict[str, str]:
        """Return JSON-compatible diagnostic fields for bridge/installer callers."""
        return asdict(self)


class PackageContractError(Exception):
    """Static validation failed; no plugin code has been executed."""

    def __init__(self, code: str, field: str, reason: str, *, path: str = ""):
        self.diagnostic = PluginDiagnostic(code, "validation", field, reason, path)
        super().__init__(f"{field}: {reason}")


class RendererActivationError(Exception):
    """A required frontend entry failed to load after backend setup succeeded.

    ``diagnostic.stage`` is the failing entry kind (``ui``, ``background`` or
    ``surface``) and ``diagnostic.state`` the state the plugin was rolled back
    to, so the diagnostic can be shown as is.
    """

    def __init__(self, diagnostic: PluginDiagnostic):
        self.diagnostic = diagnostic
        super().__init__(diagnostic.reason)
