"""QQBot application accounts and their plugin-owned C2C directory."""

from __future__ import annotations

import re
from collections.abc import Callable
from typing import Any

from shiori_sdk.storage import KeyValueStore

_ENV = re.compile(r"^\$\{([A-Za-z_][A-Za-z_0-9]*)\}$")
_KEY = "application_accounts"


def resolve_secret(value: str, resolver: Callable[[str], str]) -> str:
    """Resolve a stored environment reference only at connection time."""
    if not _ENV.fullmatch(value):
        return value
    resolved = resolver(value)
    return "" if resolved == value else resolved


class QQBotAccountStore:
    """Persist account credentials and observed targets under plugin data."""

    def __init__(self, kv: KeyValueStore) -> None:
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

    def remove(self, app_id: str) -> None:
        """Deletes an application's credential and observed targets."""
        rows = self.list()
        if any(row["app_id"] == app_id for row in rows):
            self._kv.set(_KEY, [row for row in rows if row["app_id"] != app_id])

    def set_rules(self, app_id: str, rules: dict[str, Any]) -> None:
        """Saves the host-edited response rules with the application's record."""
        self.save({**self.get(app_id), "response_rules": rules})

    def observe(self, app_id: str, openid: str) -> None:
        row = self.get(app_id)
        targets = list(row.get("targets", []))
        if openid not in targets:
            row = {**row, "targets": [*targets, openid]}
            self.save(row)
