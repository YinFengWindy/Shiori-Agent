"""One-time upgrade of legacy JSON settings into authoritative v2 plugin tables."""

from copy import deepcopy
import json
from pathlib import Path
from typing import Any

from agent.plugin_host.plugin_data import (
    migrate_plugin_file,
    plugin_data_dir,
    remove_migrated_source,
)
from agent.plugin_host.manifest import ManifestError, load_manifest
from bootstrap.paths import REPOSITORY_ROOT, plugin_roots
from infra.persistence.json_store import atomic_save_json
from infra.persistence.text_store import atomic_save_text
from infra.persistence.toml_store import render_toml

_FILENAME = "plugin_config.json"
_MARKER = "plugin_config.migrated.json"


def _legacy_sources(workspace: Path) -> dict[str, list[Path]]:
    """Uses installed manifests for identity without executing any plugin code."""
    packages: dict[str, list[Path]] = {}
    roots = dict.fromkeys(
        root.resolve() for root in [*plugin_roots(), workspace / "plugins"]
    )
    for root in roots:
        for manifest_file in sorted(root.glob("*/manifest.yaml")):
            package = manifest_file.parent
            try:
                manifest = load_manifest(package)
            except ManifestError:
                continue
            if manifest is not None:
                try:
                    plugin_data_dir(workspace, manifest.id)
                except ValueError:
                    continue
                packages.setdefault(manifest.id, []).append(package)
    sources: dict[str, list[Path]] = {}
    for plugin_id, locations in packages.items():
        if len(locations) != 1:
            # Conflicting packages have no unambiguous owner for legacy data.
            continue
        package = locations[0]
        old = REPOSITORY_ROOT / "apps/backend/plugins" / package.name
        sources[plugin_id] = list(
            dict.fromkeys(
                [
                    workspace / "plugins" / plugin_id / _FILENAME,
                    workspace / "plugins" / package.name / _FILENAME,
                    package / _FILENAME,
                    package / "backend" / _FILENAME,
                    old / _FILENAME,
                    old / "backend" / _FILENAME,
                ]
            )
        )
    return sources


def migrate_plugin_config(
    path: Path,
    data: dict[str, Any],
    *,
    workspace: Path,
) -> dict[str, Any]:
    """Archives legacy JSON then atomically persists its settings and upgrade receipt.

    The TOML receipt closes the crash window before the independent completion
    marker is saved. That marker survives later full config edits/deleted tables.
    No legacy file is removed until both authoritative settings and marker exist.
    """
    sources = _legacy_sources(workspace)
    migrated = deepcopy(data)
    metadata = data.get("_migrations", {})
    if not isinstance(metadata, dict):
        raise ValueError("_migrations 必须是对象")
    raw_receipts = metadata.get("plugin_config_json", [])
    if not isinstance(raw_receipts, list) or any(
        not isinstance(item, str) for item in raw_receipts
    ):
        raise ValueError("_migrations.plugin_config_json 必须是插件 ID 数组")
    receipts = list(raw_receipts)
    pending: list[tuple[str, Path | None, list[Path]]] = []
    for plugin_id in sorted(set(sources) | set(receipts)):
        target = plugin_data_dir(workspace, plugin_id) / _FILENAME
        marker = target.with_name(_MARKER)
        if marker.exists():
            continue
        candidates = sources.get(plugin_id, [])
        source = next((file for file in candidates if file.is_file()), None)
        if plugin_id not in receipts:
            selected = target if target.exists() else source
            if selected is None:
                continue
            values = json.loads(selected.read_text(encoding="utf-8"))
            if not isinstance(values, dict):
                raise ValueError(f"插件 {plugin_id} 的旧配置必须是 JSON 对象")
            plugins = migrated.setdefault("plugins", {})
            existing = plugins.get(plugin_id)
            # Old host toggles wrote only enabled before JSON settings moved.
            # Explicit empty tables and tables with actual v2 settings are final.
            if existing is None or set(existing) == {"enabled"}:
                plugins[plugin_id] = {**values, **(existing or {})}
            receipts.append(plugin_id)
        pending.append((plugin_id, source if not target.exists() else None, candidates))
    if not pending:
        return data
    migrated.setdefault("_migrations", {})["plugin_config_json"] = receipts
    # Validate every value before writing archives or the authoritative document.
    text = render_toml(migrated)
    for plugin_id, _, candidates in pending:
        migrate_plugin_file(
            workspace=workspace,
            plugin_id=plugin_id,
            filename=_FILENAME,
            sources=candidates,
            remove_source=False,
        )
    if migrated != data:
        atomic_save_text(path, text)
    for plugin_id, source, _ in pending:
        atomic_save_json(
            plugin_data_dir(workspace, plugin_id) / _MARKER, {"version": 1}
        )
        if source is not None:
            remove_migrated_source(source, plugin_id=plugin_id)
    return migrated
