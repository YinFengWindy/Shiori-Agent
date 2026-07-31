"""Lifecycle manager for one SQLite database per persistent world."""

from __future__ import annotations

import re
import threading
from pathlib import Path

from world_simulation.catalog import WorldCatalog
from world_simulation.repository import WorldRepository


_WORLD_ID_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")


class WorldDatabaseManager:
    """Open registered world databases and own their process-lifetime connections."""

    def __init__(self, workspace: Path, catalog: WorldCatalog) -> None:
        self.root = workspace / "worlds"
        self.root.mkdir(parents=True, exist_ok=True)
        self.catalog = catalog
        self._repositories: dict[str, WorldRepository] = {}
        self._lock = threading.RLock()

    def open(self, world_id: str) -> WorldRepository:
        """Open an existing registered world without creating paths for unknown ids."""

        with self._lock:
            existing = self._repositories.get(world_id)
            if existing is not None:
                return existing
            relative_path = self.catalog.relative_db_path(world_id)
            db_path = self._resolve_registered_path(relative_path)
            repository = WorldRepository(db_path)
            try:
                repository.require_world(world_id)
            except BaseException:
                repository.close()
                raise
            self._repositories[world_id] = repository
            return repository

    def create(self, world_id: str) -> WorldRepository:
        """Create an unregistered database for a new internally generated world id."""

        if not _WORLD_ID_PATTERN.fullmatch(world_id):
            raise ValueError(f"invalid world id: {world_id}")
        with self._lock:
            if world_id in self._repositories:
                raise ValueError(f"world database already open: {world_id}")
            db_path = self.root / world_id / "world.db"
            if db_path.exists():
                raise ValueError(f"world database already exists: {world_id}")
            repository = WorldRepository(db_path)
            self._repositories[world_id] = repository
            return repository

    def relative_path(self, world_id: str) -> str:
        """Return the portable catalog path for a newly created world database."""

        if not _WORLD_ID_PATTERN.fullmatch(world_id):
            raise ValueError(f"invalid world id: {world_id}")
        return (Path(world_id) / "world.db").as_posix()

    def discard_unregistered(self, world_id: str) -> None:
        """Remove a failed new database that was never exposed through the catalog."""

        with self._lock:
            repository = self._repositories.pop(world_id, None)
            if repository is not None:
                repository.close()
            world_dir = self.root / world_id
            for suffix in ("world.db-wal", "world.db-shm", "world.db"):
                path = world_dir / suffix
                if path.exists():
                    path.unlink()
            if world_dir.exists() and not any(world_dir.iterdir()):
                world_dir.rmdir()

    def close(self) -> None:
        """Close every cached world connection."""

        with self._lock:
            repositories = list(self._repositories.values())
            self._repositories.clear()
        for repository in repositories:
            repository.close()

    def _resolve_registered_path(self, relative_path: str) -> Path:
        candidate = (self.root / relative_path).resolve()
        root = self.root.resolve()
        if candidate == root or root not in candidate.parents:
            raise ValueError("world database path escapes the workspace")
        if not candidate.is_file():
            raise FileNotFoundError(f"world database is missing: {candidate}")
        return candidate
