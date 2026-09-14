"""Serializable contract rejection data, shared by package validation and runtime."""

from __future__ import annotations

from dataclasses import asdict, dataclass


@dataclass(frozen=True)
class PluginDiagnostic:
    """Stable host-facing failure details; reason preserves the original cause."""

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
