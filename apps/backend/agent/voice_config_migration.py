"""Move legacy cloud voice settings to their owning plugin tables atomically."""

from copy import deepcopy
from pathlib import Path
from typing import Any

from agent.config_migration_writer import save_migrated_config

_PROVIDERS = (
    ("asr", "tencent_asr", ("base_url", "secret_id", "secret_key")),
    ("tts", "minimax_tts", ("base_url", "model", "api_key", "volume")),
)


def voice_plugin_config(data: dict[str, Any]) -> dict[str, Any]:
    """Returns an idempotent upgrade preserving explicit plugin settings/references."""
    migrated = deepcopy(data)
    voice = migrated.get("voice", {})
    for kind, plugin_id, fields in _PROVIDERS:
        section = voice.get(kind, {})
        legacy = {key: section.pop(key) for key in fields if key in section}
        if not legacy:
            continue
        values = migrated.setdefault("plugins", {}).setdefault(plugin_id, {})
        for key, value in legacy.items():
            # The old cloud loader used defaults for empty endpoint/model values.
            # Omitting these overrides preserves that behavior without copying
            # provider defaults into the host or overwriting existing plugin data.
            if key in {"base_url", "model"} and not value:
                continue
            values.setdefault(key, value)
        # Preserve explicit plugin disablement; host ASR/TTS switches stay separate.
        values.setdefault("enabled", True)
    return migrated


def migrate_voice_config(path: Path, data: dict[str, Any]) -> dict[str, Any]:
    """Persists credentials and removal of old fields in one atomic document write."""
    migrated = voice_plugin_config(data)
    if migrated == data:
        return data
    from desktop_bridge.plugin_config_text import merge_table, merge_plugin_table

    def splice(text: str) -> str:
        for kind, plugin_id, fields in _PROVIDERS:
            if any(key in data.get("voice", {}).get(kind, {}) for key in fields):
                text = merge_table(text, ["voice", kind], migrated["voice"][kind])
                text = merge_plugin_table(
                    text, plugin_id, migrated["plugins"][plugin_id]
                )
        return text

    return save_migrated_config(path, migrated, splice)
