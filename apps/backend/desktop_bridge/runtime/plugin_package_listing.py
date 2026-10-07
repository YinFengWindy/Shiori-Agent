"""Project package operation journals into the existing plugin roster."""

from __future__ import annotations

from typing import Any

from agent.plugin_host.discovery import ExternalSourceDiagnostic
from desktop_bridge.runtime.plugin_package_store import PluginPackageStore


def external_source_row(source: ExternalSourceDiagnostic) -> dict[str, Any]:
    """A blocked, non-toggleable roster row for an uninstalled external source.

    It carries no renderer, trust, fingerprint or channel data: nothing may be
    granted, trusted or routed for a package that only exists as source.
    """
    manifest = source.manifest
    return {
        "id": manifest.id,
        "candidate_id": str(source.plugin_dir.absolute()),
        # Root classification (host-owned plugin root), not a loadable builtin.
        "source": "builtin",
        "directory": str(source.plugin_dir),
        "name": manifest.display_name or source.plugin_dir.name,
        "version": manifest.version or "",
        "description": manifest.desc or "",
        "renderer": {},
        "content_fingerprint": None,
        "content_hashes": {},
        "can_trust": False,
        "trust_fingerprint": None,
        "trust_directory": "",
        "trust_pending_restart": False,
        "enabled": False,
        "can_toggle": False,
        "supports_hot_unload": manifest.supports_hot_unload,
        "dependencies": list(manifest.dependencies),
        "capabilities": list(manifest.capabilities),
        "channels": [],
        "category": manifest.category,
        "state": source.diagnostic.state,
        "error": source.diagnostic.reason,
        "diagnostic": source.diagnostic.to_dict(),
        "pending_renderer_kinds": [],
        "activation_token": "",
        "account_errors": [],
        "has_config_schema": False,
    }


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
