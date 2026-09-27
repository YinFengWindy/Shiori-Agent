"""Persistent storage exposed by the plugin kv capability."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


class PluginKVStore:
    """File-backed per-plugin state, independent of plugin activation."""

    def __init__(self, path: Path) -> None:
        self._path = path

    def get(self, key: str, default: Any = None) -> Any:
        """Reads the latest persisted value, or the supplied default."""
        return self._read().get(key, default)

    def set(self, key: str, value: Any) -> None:
        """Persists one value while retaining the remaining keys."""
        # 1. 读取现有数据，写入新值，落盘
        data = self._read()
        data[key] = value
        self._write(data)

    def delete(self, key: str) -> None:
        """Removes one key; an absent key is already deleted."""
        data = self._read()
        if key in data:
            del data[key]
            self._write(data)

    def increment(self, key: str, delta: int = 1) -> int:
        """Adds delta to a persisted counter and returns its new value."""
        # 1. 读取 → 加 delta → 写回，返回新值
        data = self._read()
        new_val = int(data.get(key, 0)) + delta
        data[key] = new_val
        self._write(data)
        return new_val

    def _read(self) -> dict[str, Any]:
        if not self._path.exists():
            return {}
        return json.loads(self._path.read_text(encoding="utf-8"))

    def _write(self, data: dict[str, Any]) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        _ = self._path.write_text(
            json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8"
        )
