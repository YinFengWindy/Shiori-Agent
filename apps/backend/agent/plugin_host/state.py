"""Plugin presentation derived from admission, enablement and the SDK kernel."""

from dataclasses import dataclass, replace
from typing import Any, Literal

from shiori_sdk.kernel import KernelState, PluginDiagnostic, PluginStatus

from agent.plugin_host.call_gate import PluginCallGate
from agent.plugin_host.record import PluginRecord

type PluginViewState = Literal[
    "ACTIVE",
    "DISABLED",
    "BLOCKED",
    "FAILED",
    "UNTRUSTED",
    "CONFLICT",
    "RESTART_REQUIRED",
]

"""The seven states exposed by plugins.list, independent of transition internals."""

NOT_STARTED = PluginDiagnostic("not_started", "setup", "state", "插件尚未启动")


@dataclass
class PluginInstance:
    """Host-owned gates for one activation; lifecycle state belongs to the kernel."""

    calls: PluginCallGate
    reactivated: bool = False
    pending_renderer_kinds: frozenset[str] = frozenset()
    activation_token: str = ""


@dataclass(frozen=True)
class PluginView:
    """One immutable presentation snapshot of a discovered plugin candidate."""

    record: PluginRecord
    state: PluginViewState
    error: BaseException | None = None
    diagnostic: PluginDiagnostic | None = None
    pending_renderer_kinds: frozenset[str] = frozenset()
    activation_token: str = ""

    @property
    def plugin_id(self) -> str:
        """The manifest id; candidate_id distinguishes conflicting directories."""
        return self.record.manifest.id

    def describe(self) -> dict[str, Any]:
        """Serialize the snapshot for bridge diagnostics and logs."""
        return {
            "id": self.plugin_id,
            "candidate_id": self.record.candidate_id,
            "source": self.record.source,
            "state": self.state,
            "dir": str(self.record.plugin_dir),
            "error": str(self.error) if self.error else "",
            "diagnostic": self.diagnostic.to_dict() if self.diagnostic else None,
            "pending_renderer_kinds": sorted(self.pending_renderer_kinds),
            "activation_token": self.activation_token,
        }


def plugin_view(
    record: PluginRecord,
    enabled: bool,
    status: PluginStatus | None,
    host_failure: Exception | None,
    instance: PluginInstance | None,
) -> PluginView:
    """Apply the agreed admission/enablement/kernel precedence without storing state."""
    if admission := record.admission:
        state: PluginViewState
        match admission.state:
            case "CONFLICT":
                state = "CONFLICT"
            case "UNTRUSTED":
                state = "UNTRUSTED"
            case "RESTART_REQUIRED":
                state = "RESTART_REQUIRED"
            case _:
                state = "BLOCKED"
        return PluginView(record, state, RuntimeError(admission.reason), admission)
    if host_failure is not None:
        restart = getattr(host_failure, "code", "") == "plugin_restart_required"
        state = "RESTART_REQUIRED" if restart else "FAILED"
        diagnostic = PluginDiagnostic(
            "plugin_restart_required" if restart else "activation_failed",
            "setup",
            "activation",
            str(host_failure),
            state=state,
        )
        return PluginView(record, state, host_failure, diagnostic)
    if not enabled:
        return PluginView(record, "DISABLED")
    if status is not None and status.state is KernelState.ACTIVE:
        return PluginView(
            record,
            "ACTIVE",
            pending_renderer_kinds=(
                instance.pending_renderer_kinds if instance else frozenset()
            ),
            activation_token=instance.activation_token if instance else "",
        )
    if status is not None and status.state is KernelState.FAILED:
        if status.cleanup_errors:
            diagnostic = PluginDiagnostic(
                "rollback_cleanup_failed",
                "setup",
                "cleanup",
                "; ".join(str(error) for error in status.cleanup_errors),
                state="RESTART_REQUIRED",
            )
            return PluginView(record, "RESTART_REQUIRED", status.error, diagnostic)
        return PluginView(record, "FAILED", status.error, status.diagnostic)
    if status is not None and status.state in {
        KernelState.BLOCKED,
        KernelState.REPLACED,
    }:
        diagnostic = status.diagnostic
        assert diagnostic is not None
        field = diagnostic.field
        if field.startswith("inject["):
            index = int(field.removeprefix("inject[").removesuffix("]"))
            count = len(record.manifest.dependencies)
            field = (
                f"dependencies[{index}]"
                if index < count
                else f"inject[{index - count}]"
            )
        diagnostic = replace(diagnostic, field=field, state="BLOCKED")
        return PluginView(
            record, "BLOCKED", RuntimeError(diagnostic.reason), diagnostic
        )
    return PluginView(record, "BLOCKED", diagnostic=NOT_STARTED)
