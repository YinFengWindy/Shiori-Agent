"""Project package operation journals into the existing plugin roster."""

from __future__ import annotations

from typing import Any

from desktop_bridge.runtime.plugin_package_store import PluginPackageStore


def with_package_operations(
    rows: list[dict[str, Any]], store: PluginPackageStore
) -> list[dict[str, Any]]:
    """Keep live activation state while showing queued changes and startup failures."""
    for operation in store.list():
        if operation.status not in {"pending", "failed"}:
            continue
        target = str(store.workspace / "plugins" / operation.directory_name)
        matching = [row for row in rows if row["directory"] == target]
        if not matching:
            row = {
                "id": operation.plugin_id,
                "candidate_id": target,
                "source": "workspace",
                "directory": target,
                "name": operation.name,
                "version": operation.version,
                "description": "",
                "enabled": False,
                "can_toggle": False,
                "supports_hot_unload": False,
                "dependencies": [],
                # A queued first install has no admitted manifest yet; the row
                # still carries the list-shaped fields every other row has.
                "capabilities": [],
                "channels": [],
                "category": "feature",
                "state": (
                    "RESTART_REQUIRED" if operation.status == "pending" else "FAILED"
                ),
                "package_installed": False,
                "error": "",
                "diagnostic": None,
                "has_config_schema": False,
                "pending_renderer_kinds": [],
                "activation_token": "",
            }
            rows.append(row)
            matching = [row]
        for row in matching:
            row["package_operation_error"] = operation.error
            if operation.status == "pending":
                row["pending_operation"] = operation.action
                row["pending_version"] = operation.version
                row["can_toggle"] = False
                row["can_trust"] = False
    return rows
