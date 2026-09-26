"""QQBot application accounts and their plugin-owned C2C directory."""

from __future__ import annotations

import os
import re
from typing import Any

from agent.plugin_host.kv import PluginKVStore

_ENV = re.compile(r"^\$\{([A-Za-z_][A-Za-z_0-9]*)\}$")
_KEY = "application_accounts"


def resolve_secret(value: str) -> str:
    """Resolve a stored environment reference only at connection time."""
    match = _ENV.fullmatch(value)
    return os.environ.get(match.group(1), "") if match else value


class QQBotAccountStore:
    """Persist account credentials and observed targets under plugin data."""

    def __init__(self, kv: PluginKVStore) -> None:
        self._kv = kv

    def list(self) -> list[dict[str, Any]]:
        rows = self._kv.get(_KEY, [])
        if not isinstance(rows, list):
            raise ValueError("QQBot 账号数据格式错误")
        return rows

    def get(self, app_id: str) -> dict[str, Any]:
        return next(row for row in self.list() if row["app_id"] == app_id)

    def save(self, row: dict[str, Any]) -> None:
        rows = self.list()
        self._kv.set(
            _KEY,
            [*([item for item in rows if item["app_id"] != row["app_id"]]), row],
        )

    def migrate_legacy(self, app_id: str, secret: str) -> None:
        """Import the former single application exactly once, preserving its C2C IDs."""
        if (
            not app_id
            or not secret
            or any(row["app_id"] == app_id for row in self.list())
        ):
            return
        self.save(
            {
                "app_id": app_id,
                "client_secret": secret,
                "legacy": True,
                "connected": True,
                "targets": [],
            }
        )

    def observe(self, app_id: str, openid: str) -> None:
        row = self.get(app_id)
        targets = list(row.get("targets", []))
        if openid not in targets:
            row = {**row, "targets": [*targets, openid]}
            self.save(row)
