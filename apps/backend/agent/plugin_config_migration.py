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
from agent.plugin_host.discovery import discover_plugins
from bootstrap.paths import REPOSITORY_ROOT, plugin_roots
from infra.persistence.json_store import atomic_save_json
from infra.persistence.text_store import atomic_save_text
from infra.persistence.toml_store import render_toml

_FILENAME = "plugin_config.json"
_MARKER = "plugin_config.migrated.json"


def _legacy_sources(workspace: Path) -> dict[str, list[Path]]:
    """Uses installed manifests for identity without executing any plugin code."""
    external_root = workspace / "plugins"
    records = discover_plugins(
        [*plugin_roots(), external_root],
        external_roots=[external_root],
        namespace="config_migration",
        strict=False,
        host=None,
    )
    package_directories = {record.plugin_dir.absolute() for record in records}
    directory_identities: dict[str, set[str]] = {}
    for record in records:
        directory_identities.setdefault(record.name, set()).add(record.manifest.id)
    sources: dict[str, list[Path]] = {}
    for record in records:
        if record.source != "builtin" or record.admission is not None:
            continue
        plugin_id = record.manifest.id
        try:
            plugin_data_dir(workspace, plugin_id)
        except ValueError:
            continue
        package = record.plugin_dir
        legacy_names = [plugin_id]
        if directory_identities[record.name] == {plugin_id}:
            legacy_names.append(record.name)
        legacy_names = list(dict.fromkeys(legacy_names))
        # A discovered workspace package owns its own JSON, regardless of its
        # admission. Only manifest-free old data directories can supply aliases.
        workspace_files = [
            external_root / name / _FILENAME
            for name in legacy_names
            if (external_root / name).absolute() not in package_directories
        ]
        old_root = REPOSITORY_ROOT / "apps/backend/plugins"
        sources[plugin_id] = [
            *workspace_files,
            package / _FILENAME,
            package / "backend" / _FILENAME,
            *(
                old_root / name / subpath
                for name in legacy_names
                for subpath in (_FILENAME, f"backend/{_FILENAME}")
            ),
        ]
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
    for plugin_id in sorted(sources):
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
