"""Retire copied QQ host connection fields after the plugin records a receipt."""

from __future__ import annotations

from copy import deepcopy
import json
from pathlib import Path
from typing import Any

from agent.config_migration_writer import save_migrated_config
from agent.legacy_config_receipt import legacy_config_digest

_OLD_CONNECTION_FIELDS = (
    "bot_uin",
    "ws_uri",
    "ws_token",
    "websocket_open_timeout_seconds",
)


def retire_copied_qq_config(
    path: Path, data: dict[str, Any], *, workspace: Path
) -> dict[str, Any]:
    """Remove only connection values the QQ plugin confirmed it copied."""
    receipt = workspace / "plugin-data" / "qq" / "legacy-host-config.migrated.json"
    if not receipt.is_file():
        return data
    plugins = data.get("plugins")
    if not isinstance(plugins, dict):
        return data
    qq = plugins.get("qq")
    if not isinstance(qq, dict) or not any(key in qq for key in _OLD_CONNECTION_FIELDS):
        return data
    from agent.config import resolve_config_references

    source = resolve_config_references(qq)
    source_hash = legacy_config_digest(
        {
            "bot_uin": str(source.get("bot_uin") or "").strip(),
            "ws_uri": str(source.get("ws_uri") or "").strip(),
            "ws_token": str(source.get("ws_token") or "").strip(),
            "websocket_open_timeout_seconds": float(
                source.get("websocket_open_timeout_seconds", 5.0)
            ),
        }
    )
    receipt_data = json.loads(receipt.read_text(encoding="utf-8"))
    if receipt_data != {"version": 1, "source_hash": source_hash}:
        return data

    from desktop_bridge.plugin_config_text import (
        merge_plugin_table,
        remove_plugin_table,
    )

    migrated = deepcopy(data)
    remaining = migrated["plugins"]["qq"]
    for key in _OLD_CONNECTION_FIELDS:
        remaining.pop(key, None)
    if not remaining:
        del migrated["plugins"]["qq"]

    def splice(text: str) -> str:
        return (
            merge_plugin_table(text, "qq", remaining)
            if remaining
            else remove_plugin_table(text, "qq")
        )

    return save_migrated_config(path, migrated, splice)
