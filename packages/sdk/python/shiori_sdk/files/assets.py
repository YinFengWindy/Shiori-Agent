"""Immutable, content-addressed copies owned by a durable content store."""

from __future__ import annotations

import hashlib
import os
import shutil
import tempfile
from pathlib import Path


def copy_owned_asset(source: Path, directory: Path) -> Path:
    """Stream a regular asset into an atomic copy without modifying its source."""
    directory.mkdir(parents=True, exist_ok=True)
    descriptor, temporary = tempfile.mkstemp(dir=directory, prefix=".asset-")
    try:
        with os.fdopen(descriptor, "wb") as copied, source.open("rb") as original:
            shutil.copyfileobj(original, copied)
            copied.flush()
            os.fsync(copied.fileno())
        with Path(temporary).open("rb") as copied:
            digest = hashlib.file_digest(copied, "sha256").hexdigest()
        target = directory / f"{digest[:32]}{source.suffix.lower()}"
        if target.exists():
            with target.open("rb") as existing:
                if hashlib.file_digest(existing, "sha256").hexdigest() != digest:
                    raise ValueError(f"素材目标内容冲突: {target}")
            return target
        os.replace(temporary, target)
        return target
    finally:
        Path(temporary).unlink(missing_ok=True)
