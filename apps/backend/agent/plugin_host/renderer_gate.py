"""Per-activation renderer readiness and failure reports (#262)."""

from collections.abc import Collection, Mapping
from uuid import uuid4
from shiori_sdk.kernel import Kernel, PluginDiagnostic, RendererActivationError
from agent.plugin_host.record import PluginRecord
from agent.plugin_host.state import PluginInstance

# #262 AC1: ui/background readiness gates the fully ACTIVE presentation;
# backend contributions are already live and this gate grants no resources.
# Surface windows are opened on demand, so they do not gate initial readiness.
# A surface failure still rolls back the plugin, like ui/background failures.
_RENDERER_GATED_KINDS: tuple[str, ...] = ("ui", "background")


def required_renderer_kinds(record: PluginRecord) -> frozenset[str]:
    """Returns the manifest's declared renderer kinds that gate ACTIVE display."""
    frontend = record.manifest.metadata.get("frontend", {})
    if isinstance(frontend, dict) and "exports" in frontend:
        return frozenset(
            kind for kind in _RENDERER_GATED_KINDS if kind in frontend["exports"]
        )
    return frozenset()


def mark_pending(instance: PluginInstance, record: PluginRecord) -> None:
    """Mint a fresh attempt token and retain the required renderer entry kinds."""
    instance.pending_renderer_kinds = required_renderer_kinds(record)
    instance.activation_token = uuid4().hex


def find_active_instance(
    plugin_id: str,
    activation_token: str,
    instances: Mapping[str, PluginInstance],
    active_plugin_ids: Collection[str],
) -> PluginInstance | None:
    """Reject reports from an inactive or superseded activation attempt."""
    instance = instances.get(plugin_id)
    if (
        instance is not None
        and instance.activation_token == activation_token
        and plugin_id in active_plugin_ids
    ):
        return instance
    return None


def confirm_entry(
    plugin_id: str,
    kind: str,
    activation_token: str,
    *,
    instances: Mapping[str, PluginInstance],
    active_plugin_ids: Collection[str],
) -> bool:
    """Confirm one renderer contribution without changing backend resource grants."""
    instance = find_active_instance(
        plugin_id, activation_token, instances, active_plugin_ids
    )
    if instance is None or kind not in instance.pending_renderer_kinds:
        return False
    instance.pending_renderer_kinds -= {kind}
    return True


async def fail_entry(
    plugin_id: str,
    kind: str,
    reason: str,
    activation_token: str,
    *,
    kernel: Kernel,
    instances: dict[str, PluginInstance],
    active_plugin_ids: Collection[str],
) -> bool:
    """Rollback a current attempt; the caller holds the transition lock."""
    instance = find_active_instance(
        plugin_id, activation_token, instances, active_plugin_ids
    )
    if instance is None:
        return False
    diagnostic = PluginDiagnostic(
        f"renderer_{kind}_failed",
        kind,
        "frontend.entry",
        reason,
        state="FAILED",
    )
    instance.calls.retire()
    await kernel.deactivate(plugin_id, diagnostic, RendererActivationError(diagnostic))
    instances.pop(plugin_id)
    return True
