"""Atomic file persistence shared by configuration and cache writers."""

import os
from pathlib import Path
from tempfile import NamedTemporaryFile


def atomic_save_bytes(path: Path, content: bytes) -> None:
    """Durably replaces a file; interrupted writes leave the old file intact."""
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary: Path | None = None
    try:
        with NamedTemporaryFile(
            mode="wb",
            dir=path.parent,
            prefix=f".{path.name}.",
            delete=False,
        ) as stream:
            temporary = Path(stream.name)
            stream.write(content)
            stream.flush()
            os.fsync(stream.fileno())
        temporary.replace(path)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def atomic_save_text(path: Path, content: str) -> None:
    """Durably replaces a UTF-8 file; interrupted writes leave the old file intact."""
    atomic_save_bytes(path, content.encode("utf-8"))
