"""Move the remaining legacy plugin files before any runtime readers start."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

from shiori_sdk.files.text import atomic_save_bytes
from shiori_sdk.storage import plugin_data_dir

# Explicit upgrade inputs only: shared memory, role state and user recovery
# files have different owners and must never be swept up by this migration.
_FILES = (
    ("scene/state.json", "scene", "state.json", dict),
    ("schedules.json", "schedule", "schedules.json", list),
    ("mcp_servers.json", "mcp", "mcp_servers.json", dict),
    (
        "memory/proactive_config_trace.jsonl",
        "proactive",
        "logs/proactive_config_trace.jsonl",
        None,
    ),
    (
        "memory/proactive_rate_trace.jsonl",
        "proactive",
        "logs/proactive_rate_trace.jsonl",
        None,
    ),
)


def migrate_plugin_data_paths(workspace: Path) -> None:
    """Publish missing targets, verify a recovery copy, then remove old files.

    Existing targets are authoritative, including empty state. Archives are
    never migration inputs, so deleting plugin data cannot resurrect a backup.
    A failure leaves the source available and stops startup; retries can finish
    a partially published file without overwriting the new location.
    """
    for relative, plugin_id, filename, root_type in _FILES:
        source = workspace / relative
        if not source.exists():
            continue
        content = source.read_bytes()
        target = plugin_data_dir(workspace, plugin_id) / filename
        if not target.exists():
            if root_type is not None and not isinstance(json.loads(content), root_type):
                raise ValueError(f"插件旧数据格式无效: {source}")
            atomic_save_bytes(target, content)
            if target.read_bytes() != content:
                raise OSError(f"插件数据迁移校验失败: {target}")

        digest = hashlib.sha256(content).hexdigest()
        archive = workspace / "private_runtime" / "plugin-storage-archive" / relative
        archive = archive.with_name(f"{archive.name}.{digest}.bak")
        if not archive.exists():
            atomic_save_bytes(archive, content)
        if archive.read_bytes() != content:
            raise OSError(f"插件数据归档校验失败: {archive}")
        # Do not remove bytes written by another process during the copy.
        if source.read_bytes() != content:
            raise OSError(f"插件旧数据在迁移期间变化，请关闭其他实例后重试: {source}")
        source.unlink()
