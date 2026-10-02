"""Upgrade old plugin disable markers into authoritative persisted preferences."""

from __future__ import annotations

from copy import deepcopy
from pathlib import Path
from typing import Any

from bootstrap.paths import REPOSITORY_ROOT, plugin_roots
from agent.plugin_host.manifest import ManifestError, load_manifest
from shiori_sdk.files.text import atomic_save_text
from infra.persistence.toml_store import render_toml


def migrate_plugin_preferences(path: Path, data: dict[str, Any]) -> dict[str, Any]:
    """Persists missing enable flags before startup; explicit choices always win.

    Markers are retained as upgrade evidence, including on read-only installs.
    Once a flag is persisted, the marker never overrides it. Candidate parsing
    deliberately does not call this migration. Retired core features keep their
    own migration and are not recreated as plugin configuration.
    """
    current_roots = plugin_roots()
    roots = [*current_roots, REPOSITORY_ROOT / "apps/backend/plugins"]
    marked_directories = {
        marker.parent.name
        for root in roots
        if root.is_dir()
        for marker in root.glob("*/plugin.disabled")
        if marker.is_file()
        and marker.parent.name not in {"scene_awareness", "relationship_proactive"}
    }
    if not marked_directories:
        return data
    # Configuration keys use manifest IDs, while old markers use directory names.
    # Mirror discovery's first-directory-wins rule. Uninstalled/invalid packages
    # retain their markers until an actual current identity can be established.
    identities: dict[str, str] = {}
    for root in current_roots:
        for directory in sorted(marked_directories - identities.keys()):
            try:
                manifest = load_manifest(root / directory)
            except ManifestError:
                continue
            if manifest is not None:
                identities[directory] = manifest.id
    disabled = set(identities.values())
    plugins = data.get("plugins", {})
    missing = [
        plugin_id
        for plugin_id in sorted(disabled)
        if "enabled" not in plugins.get(plugin_id, {})
    ]
    if not missing:
        return data
    migrated = deepcopy(data)
    for plugin_id in missing:
        migrated.setdefault("plugins", {}).setdefault(plugin_id, {})["enabled"] = False
    # Structural serialization covers inline/dotted tables as well as headers.
    # Reject an unrepresentable document before touching either data or markers.
    text = render_toml(migrated)
    atomic_save_text(path, text)
    return migrated
