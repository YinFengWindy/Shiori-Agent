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


class RendererActivationError(Exception):
    """A required ``renderer.<kind>`` entry failed after backend setup succeeded.

    Raised internally by ``PluginKernel.fail_renderer_entry`` (#262) when a
    renderer process (main window UI, plugin-host background, or a surface
    window) reports that its admitted ``ui``/``background``/``surface`` entry
    could not load. ``diagnostic.stage`` is the failing kind itself
    (``"ui"``, ``"background"`` or ``"surface"``) — a new, valid value for
    ``PluginDiagnostic.stage`` alongside the existing
    ``"validation"``/``"discovery"``/``"trust"``/``"dependency"`` stages.
    """

    def __init__(self, diagnostic: PluginDiagnostic):
        self.diagnostic = diagnostic
        super().__init__(diagnostic.reason)


class ChannelDeclarationError(Exception):
    """``ctx.channels.add`` 贡献了 manifest ``channels`` 未声明的渠道名。

    setup 期间抛出，内核按普通 setup 失败回滚为 ``FAILED``；诊断的 ``state``
    与回滚后的真实状态一致，因此 ``PluginHandle`` 可以直接展示它。
    """

    def __init__(self, plugin_id: str, channel: str, declared: frozenset[str]):
        names = ", ".join(sorted(declared)) or "（无）"
        self.diagnostic = PluginDiagnostic(
            code="undeclared_channel",
            stage="setup",
            field="channels",
            reason=(
                f"插件 {plugin_id} 贡献了未在 manifest channels 中声明的渠道 "
                f"{channel}；已声明: {names}"
            ),
            state="FAILED",
        )
        super().__init__(self.diagnostic.reason)
