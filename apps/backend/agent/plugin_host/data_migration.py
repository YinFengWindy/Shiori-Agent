"""One-time publication of private data before an owning store opens it."""

from __future__ import annotations

import json
import shutil
import threading
from pathlib import Path

from infra.persistence.json_store import atomic_save_json
from infra.persistence.sqlite_lifecycle import require_inactive_data

from .data_snapshot import data_digest, snapshot_data
from .plugin_data import plugin_data_dir

_LOCK = threading.RLock()


def migrate_private_data(
    workspace: Path, plugin_id: str, name: str, source: Path
) -> Path:
    """Publish an artifact once, preserving old data and rejecting target conflicts.

    Receipts deliberately live outside the deletable plugin root. Removing plugin
    data is an explicit reset and must never resurrect a retained migration source.
    Sources remain upgrade backups until their owner has updated all references.
    """
    root = plugin_data_dir(workspace, plugin_id)
    if not name or Path(name).name != name or name in {".", ".."}:
        raise ValueError("插件数据名称必须是单个路径段")
    target = root / name
    receipt = (
        workspace / "private_runtime" / "plugin-data-migrations" / plugin_id
    ) / f"{name}.json"
    with _LOCK:
        if receipt.exists():
            state = json.loads(receipt.read_text(encoding="utf-8"))
            if state["status"] == "complete":
                return target
            if target.exists():
                if data_digest(target) != state["digest"]:
                    raise ValueError(f"插件数据迁移目标冲突: {target}")
                atomic_save_json(receipt, {"status": "complete"})
                return target
        elif target.exists():
            if source.exists():
                raise ValueError(f"插件数据迁移目标已存在，保留两份数据: {target}")
            atomic_save_json(receipt, {"status": "complete"})
            return target
        if not source.exists():
            atomic_save_json(receipt, {"status": "complete"})
            return target
        root.mkdir(parents=True, exist_ok=True)
        staging = root / f".{name}.migration"
        if staging.exists():
            _remove_staging(staging)
        try:
            with require_inactive_data(source):
                snapshot_data(source, staging)
                atomic_save_json(
                    receipt, {"status": "prepared", "digest": data_digest(staging)}
                )
                staging.rename(target)
                atomic_save_json(receipt, {"status": "complete"})
        finally:
            if staging.exists():
                _remove_staging(staging)
        return target


def _remove_staging(path: Path) -> None:
    if path.is_dir():
        shutil.rmtree(path)
    else:
        path.unlink()
