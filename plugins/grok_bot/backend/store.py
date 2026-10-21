"""Plugin-owned connection records; shared host account state stays authoritative."""

import json
import os
from pathlib import Path

from shiori_sdk.storage import KeyValueStore, read_mapping

from .config import ConnectionConfig, read_connection


class ConnectionStore:
    """Persist role-owned settings independently from their runtime connection."""

    def __init__(self, kv: KeyValueStore) -> None:
        self.kv = kv

    def rows(self) -> dict[str, object]:
        """Return raw records so a corrupt account can be rejected independently."""
        return read_mapping(self.kv, "connections")

    def get(self, connection_id: str) -> ConnectionConfig:
        """Read one validated saved record."""
        return read_connection(self.rows()[connection_id])

    def save(self, config: ConnectionConfig) -> None:
        """Atomically replace one account inside the plugin's KV transaction."""
        self.kv.set(
            "connections", {**self.rows(), config.connection_id: config.model_dump()}
        )

    def remove(self, connection_id: str) -> None:
        """Remove only the deleted connection's settings."""
        rows = self.rows()
        rows.pop(connection_id, None)
        self.kv.set("connections", rows)


def write_private_json(path: Path, value: dict[str, object]) -> None:
    """Replace a local callback file without exposing partial credentials."""
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(".tmp")
    try:
        fd = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            json.dump(value, stream, ensure_ascii=False)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)
