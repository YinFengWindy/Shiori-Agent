"""Runtime resource retirement before a restart-only package removal."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from agent.plugin_host.handle import PluginRecord
from agent.plugin_host.package_fingerprint import inspect_package_content
from desktop_bridge.runtime.apply import RuntimeApplyError
from desktop_bridge.runtime.plugin_package_store import (
    PackageOperation,
    PluginPackageStore,
    application_session,
)

if TYPE_CHECKING:
    from desktop_bridge.runtime.plugin_management import RuntimePluginManagement


async def schedule_plugin_uninstall(
    management: RuntimePluginManagement,
    store: PluginPackageStore,
    record: PluginRecord,
    payload: dict[str, Any],
    **apply_callbacks,
) -> dict[str, Any]:
    """Respect the hot-unload contract, then persist the user's independent data choice."""
    candidate_id = record.candidate_id
    delete_data = payload.get("delete_data", False)
    fingerprint = inspect_package_content(record.plugin_dir).fingerprint
    row = next(
        row
        for row in management.list({})["plugins"]
        if row["candidate_id"] == candidate_id
    )
    if row["enabled"] and row["can_toggle"]:
        try:
            await management.set_enabled(
                {
                    "plugin_id": record.manifest.id,
                    "enabled": False,
                    "operation_id": payload["operation_id"],
                },
                **apply_callbacks,
            )
        except RuntimeApplyError as exc:
            # The existing generation contract can also require restart
            # for an active dependent. Never force that runtime to unload.
            if exc.code != "plugin_restart_required":
                raise
    token, _ = store.create_directory()
    operation = PackageOperation(
        token=token,
        plugin_id=record.manifest.id,
        name=record.manifest.display_name or record.name,
        version=record.manifest.version or "",
        directory_name=record.plugin_dir.name,
        action="uninstall",
        session=application_session(),
        status="pending",
        original_fingerprint=fingerprint,
        delete_data=delete_data,
    )
    try:
        store.save(operation)
        store.clear_failures(operation.plugin_id)
    except BaseException:
        store.remove(token)
        raise
    return {"plugin_id": operation.plugin_id, "restart_required": True}
