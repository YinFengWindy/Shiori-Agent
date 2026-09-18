"""NovelAI's data root and one-time normalization of persisted image paths."""

from __future__ import annotations

import json
from pathlib import Path

from agent.plugin_host.data_migration import migrate_private_data
from infra.persistence.json_store import atomic_save_json
from infra.persistence.text_store import atomic_save_text


def storage_root(workspace: Path) -> Path:
    """Migrate generation artifacts without removing cross-owner legacy sources."""
    old = workspace / "private_runtime" / "novelai"
    root = migrate_private_data(workspace, "novelai", "generation", old)
    marker = root / ".paths-migrated.json"
    if marker.exists() or not root.exists():
        return root
    index = root / "records.jsonl"
    if index.exists():
        records = [
            json.loads(line)
            for line in index.read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]
        for record in records:
            paths = record.get("output_paths", [])
            record.setdefault("original_output_paths", paths)
            record["output_paths"] = [
                _move_path(workspace, old, root, path) for path in paths
            ]
            record["base_image_path"] = _move_path(
                workspace, old, root, record.get("base_image_path", "")
            )
        atomic_save_text(
            index,
            "".join(
                json.dumps(record, ensure_ascii=False) + "\n" for record in records
            ),
        )
        for record in records:
            for value in record["output_paths"]:
                meta = Path(value).parent / "meta.json"
                if meta.is_file() and meta.resolve().is_relative_to(root.resolve()):
                    atomic_save_json(meta, record)
    atomic_save_json(marker, {"version": 1})
    return root


def _move_path(workspace: Path, old: Path, root: Path, value: str) -> str:
    if not value:
        return value
    path = Path(value)
    if not path.is_absolute():
        path = workspace / path
    if path.resolve().is_relative_to(old.resolve()):
        return str(root / path.resolve().relative_to(old.resolve()))
    return value
