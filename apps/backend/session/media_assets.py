"""Session-owned media copies and their original generation provenance."""

from __future__ import annotations

import hashlib
import json
import mimetypes
import threading
from pathlib import Path

from shiori_sdk.files.text import atomic_save_text
from shiori_sdk.files.assets import copy_owned_asset

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
