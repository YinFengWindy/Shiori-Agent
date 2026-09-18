"""Track live database owners so migration cannot strand a runtime writer."""

from __future__ import annotations

import sqlite3
import threading
import weakref
from contextlib import contextmanager
from pathlib import Path

_LOCK = threading.RLock()
_CONNECTIONS: weakref.WeakSet[_TrackedConnection] = weakref.WeakSet()


class _TrackedConnection(sqlite3.Connection):
    def __init__(self, database, *args, **kwargs):
        super().__init__(database, *args, **kwargs)
        self.owned_path = Path(database).resolve()
        _CONNECTIONS.add(self)

    def close(self) -> None:
        with _LOCK:
            super().close()
            _CONNECTIONS.discard(self)


def open_owned_database(path: Path, **kwargs) -> sqlite3.Connection:
    """Open a tracked owning connection; failed opens never acquire a lease."""
    with _LOCK:
        return sqlite3.connect(str(path), factory=_TrackedConnection, **kwargs)


@contextmanager
def require_inactive_data(source: Path):
    """Hold migration against new opens and reject still-live source owners."""
    root = source.resolve()
    with _LOCK:
        if any(
            connection.owned_path == root or connection.owned_path.is_relative_to(root)
            for connection in _CONNECTIONS
        ):
            raise RuntimeError(f"旧插件数据库仍在使用，请重启后迁移: {source}")
        yield
