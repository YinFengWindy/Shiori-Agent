"""Validated copies of plugin files, including committed SQLite WAL contents."""

from __future__ import annotations

import hashlib
import shutil
import sqlite3
from contextlib import closing
from pathlib import Path


def snapshot_data(source: Path, target: Path) -> None:
    """Copy one private artifact; SQLite connections are closed before returning."""
    if source.is_symlink():
        raise ValueError(f"插件旧数据不能是符号链接: {source}")
    if source.is_dir():
        target.mkdir()
        for child in source.iterdir():
            # The backup API includes committed WAL pages; sidecars must not be copied.
            if (
                child.name.endswith(("-wal", "-shm", "-journal"))
                and Path(str(child).rsplit("-", 1)[0]).is_file()
            ):
                continue
            snapshot_data(child, target / child.name)
    elif source.suffix == ".db":
        with closing(
            sqlite3.connect(source.resolve().as_uri() + "?mode=ro", uri=True)
        ) as old:
            with closing(sqlite3.connect(target)) as new:
                old.backup(new)
                # Reading the schema proves the snapshot can be opened without
                # requiring optional virtual-table extensions on this connection.
                new.execute("SELECT count(*) FROM sqlite_master").fetchone()
    else:
        shutil.copyfile(source, target)


def data_digest(path: Path) -> dict[str, str]:
    """Fingerprint a prepared artifact for interrupted publication recovery."""
    files = sorted(path.rglob("*")) if path.is_dir() else [path]
    return {
        (file.relative_to(path).as_posix() if path.is_dir() else "."): _file_digest(
            file
        )
        for file in files
        if file.is_file()
    }


def _file_digest(path: Path) -> str:
    with path.open("rb") as handle:
        return hashlib.file_digest(handle, "sha256").hexdigest()
