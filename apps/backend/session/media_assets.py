"""Session-owned media copies and their original generation provenance."""

from __future__ import annotations

import hashlib
import json
import mimetypes
import sqlite3
import threading
from pathlib import Path

from infra.persistence.text_store import atomic_save_text
from infra.persistence.owned_assets import copy_owned_asset

_MEDIA_LOCK = threading.RLock()


def preserve_media(workspace: Path, paths: list[str]) -> list[str]:
    """Adopt existing local images before a message commits their references."""
    root = workspace.resolve() / "sessions" / "media"
    result = []
    for value in paths:
        if "://" in value or value.startswith("data:"):
            result.append(value)
            continue
        mime_type = mimetypes.guess_type(value)[0] or ""
        if not mime_type.startswith("image/"):
            result.append(value)
            continue
        source = Path(value)
        if not source.is_absolute():
            source = workspace / source
        source = source.resolve()
        if source.is_relative_to(root) or not source.is_file():
            result.append(value)
            continue
        identity = hashlib.sha256(str(source).encode("utf-8")).hexdigest()[:24]
        directory = root / identity
        with _MEDIA_LOCK:
            target = copy_owned_asset(source, directory)
            metadata = directory / "source.json"
            if (
                metadata.exists()
                and Path(json.loads(metadata.read_text(encoding="utf-8"))["path"])
                != source
            ):
                raise ValueError(f"会话素材来源冲突: {metadata}")
            if not metadata.exists():
                atomic_save_text(
                    metadata, json.dumps({"path": str(source)}, ensure_ascii=False)
                )
        result.append(str(target))
    return result


def original_media_path(workspace: Path, value: str) -> str:
    """Resolve provenance only for a copy inside the session-owned media root."""
    path = Path(value)
    if not path.is_absolute():
        path = workspace / path
    path = path.resolve()
    root = workspace.resolve() / "sessions" / "media"
    if not path.is_relative_to(root):
        return value
    metadata = path.parent / "source.json"
    return str(json.loads(metadata.read_text(encoding="utf-8"))["path"])


def adopt_persisted_media(connection: sqlite3.Connection, workspace: Path) -> None:
    """Migrate message references atomically after all required copies exist."""
    with connection:
        connection.execute("BEGIN IMMEDIATE")
        connection.execute(
            "CREATE TABLE IF NOT EXISTS media_migrations (version INTEGER PRIMARY KEY)"
        )
        if connection.execute(
            "SELECT 1 FROM media_migrations WHERE version = 1"
        ).fetchone():
            return
        rows = connection.execute(
            "SELECT id, media FROM messages WHERE media IS NOT NULL"
        ).fetchall()
        updates = []
        for row in rows:
            old = json.loads(row["media"])
            new = preserve_media(workspace, old)
            if new != old:
                updates.append((json.dumps(new, ensure_ascii=False), row["id"]))
        connection.executemany("UPDATE messages SET media = ? WHERE id = ?", updates)
        connection.execute("INSERT INTO media_migrations VALUES (1)")
