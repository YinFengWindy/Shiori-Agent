"""Shared migration of retired plugin switches into explicitly owned core features."""

from pathlib import Path
from typing import Any
import tomllib

from desktop_bridge.plugin_config_text import merge_table
from shiori_sdk.files.text import atomic_save_text


def load_boolean_preferences(
    data: dict[str, Any], *, section: str, keys: tuple[str, ...], legacy_id: str
) -> dict[str, bool]:
    """Validates core switches, filling omitted keys from their legacy plugin preference."""
    raw = data.get("agent", {}).get(section, {})
    if not isinstance(raw, dict) or set(raw) - set(keys):
        raise ValueError(f"agent.{section} only accepts {', '.join(keys)}")
    if any(not isinstance(value, bool) for value in raw.values()):
        raise ValueError(f"agent.{section} switches must be boolean")
    enabled = bool(data.get("plugins", {}).get(legacy_id, {}).get("enabled", True))
    return {key: raw.get(key, enabled) for key in keys}


def migrate_boolean_preferences(
    path: Path,
    data: dict[str, Any],
    *,
    section: str,
    keys: tuple[str, ...],
    legacy_id: str,
    roots: tuple[Path, ...],
) -> dict[str, Any]:
    """Atomically persists only missing core choices, without touching other user files.

    Existing core keys always win. Read-only legacy markers need not be removed:
    once all core keys exist, their old values are never consulted again.
    """
    current = data.get("agent", {}).get(section, {})
    values = load_boolean_preferences(
        data, section=section, keys=keys, legacy_id=legacy_id
    )
    missing = [key for key in keys if key not in current]
    if not missing:
        return data
    disabled = any((root / legacy_id / "plugin.disabled").is_file() for root in roots)
    if data.get("plugins", {}).get(legacy_id) is None and not disabled:
        return data
    if disabled:
        values.update({key: False for key in missing})
    text = path.read_text(encoding="utf-8")
    migrated = merge_table(text, ["agent", section], values)
    parsed = tomllib.loads(migrated)
    atomic_save_text(path, migrated)
    return parsed
