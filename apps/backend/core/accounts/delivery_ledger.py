"""Durable account delivery attempts independent of conversation turn commits."""

from __future__ import annotations

import json
import sqlite3
from contextlib import closing
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal
from uuid import uuid4

DeliveryStatus = Literal["pending", "sent", "failed"]


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass(frozen=True)
class AccountDeliveryAttempt:
    """One selected account target and its last confirmed delivery state."""

    attempt_id: str
    role_id: str
    account_id: str
    target_kind: str
    target_id: str
    target_options: dict[str, Any]
    source: str
    status: DeliveryStatus
    platform_message_id: str | None
    error: str | None
    created_at: str
    updated_at: str


class AccountDeliveryLedger:
    """Commits each attempt before transport side effects and updates it afterward."""

    def __init__(self, workspace: Path) -> None:
        workspace.mkdir(parents=True, exist_ok=True)
        self._path = workspace / "account_deliveries.sqlite3"
        with closing(sqlite3.connect(self._path)) as connection:
            with connection:
                connection.execute("""
                    CREATE TABLE IF NOT EXISTS account_delivery_attempts (
                        attempt_id TEXT PRIMARY KEY,
                        role_id TEXT NOT NULL,
                        account_id TEXT NOT NULL,
                        target_kind TEXT NOT NULL,
                        target_id TEXT NOT NULL,
                        target_options TEXT NOT NULL,
                        source TEXT NOT NULL,
                        status TEXT NOT NULL CHECK (status IN ('pending', 'sent', 'failed')),
                        platform_message_id TEXT,
                        error TEXT,
                        created_at TEXT NOT NULL,
                        updated_at TEXT NOT NULL
                    )
                    """)
                connection.execute("""
                    CREATE INDEX IF NOT EXISTS account_delivery_attempts_by_role
                    ON account_delivery_attempts (role_id, created_at)
                    """)

    def begin(
        self,
        *,
        role_id: str,
        account_id: str,
        target_kind: str,
        target_id: str,
        target_options: dict[str, Any],
        source: str,
    ) -> AccountDeliveryAttempt:
        """Durably records a selected target before any plugin call can start."""
        attempt_id = uuid4().hex
        created_at = _now()
        with closing(sqlite3.connect(self._path, timeout=10)) as connection:
            with connection:
                connection.execute(
                    """
                    INSERT INTO account_delivery_attempts
                    (attempt_id, role_id, account_id, target_kind, target_id,
                     target_options, source, status, created_at, updated_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, 'pending', ?, ?)
                    """,
                    (
                        attempt_id,
                        role_id,
                        account_id,
                        target_kind,
                        target_id,
                        json.dumps(target_options, ensure_ascii=False),
                        source,
                        created_at,
                        created_at,
                    ),
                )
        return self.get(attempt_id)

    def mark_sent(self, attempt_id: str, platform_message_id: str) -> None:
        """Store only the platform's nonblank acceptance receipt."""
        if not platform_message_id.strip():
            raise ValueError("平台回执不能为空")
        self._finish(attempt_id, status="sent", platform_message_id=platform_message_id)

    def mark_failed(self, attempt_id: str, error: str) -> None:
        """Record a definite failure; uncertain transport outcomes stay pending."""
        self._finish(attempt_id, status="failed", error=error)

    def mark_uncertain(self, attempt_id: str, error: str) -> None:
        """Keep an unresolved attempt pending while retaining its error type."""
        self._finish(attempt_id, status="pending", error=error)

    def _finish(
        self,
        attempt_id: str,
        *,
        status: DeliveryStatus,
        platform_message_id: str | None = None,
        error: str | None = None,
    ) -> None:
        with closing(sqlite3.connect(self._path, timeout=10)) as connection:
            with connection:
                updated = connection.execute(
                    """
                    UPDATE account_delivery_attempts
                    SET status = ?, platform_message_id = ?, error = ?, updated_at = ?
                    WHERE attempt_id = ? AND status = 'pending'
                    """,
                    (status, platform_message_id, error, _now(), attempt_id),
                )
                if updated.rowcount != 1:
                    raise RuntimeError("账号投递尝试不存在或已完成")

    def get(self, attempt_id: str) -> AccountDeliveryAttempt:
        """Read one persisted attempt, including a pending uncertain outcome."""
        with closing(sqlite3.connect(self._path, timeout=10)) as connection:
            connection.row_factory = sqlite3.Row
            row = connection.execute(
                "SELECT * FROM account_delivery_attempts WHERE attempt_id = ?",
                (attempt_id,),
            ).fetchone()
        if row is None:
            raise KeyError(attempt_id)
        return self._from_row(row)

    @staticmethod
    def _from_row(row: sqlite3.Row) -> AccountDeliveryAttempt:
        return AccountDeliveryAttempt(
            attempt_id=row["attempt_id"],
            role_id=row["role_id"],
            account_id=row["account_id"],
            target_kind=row["target_kind"],
            target_id=row["target_id"],
            target_options=json.loads(row["target_options"]),
            source=row["source"],
            status=row["status"],
            platform_message_id=row["platform_message_id"],
            error=row["error"],
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )

    def list_for_role(self, role_id: str) -> list[AccountDeliveryAttempt]:
        """Return all selected targets for a role, including failed attempts."""
        with closing(sqlite3.connect(self._path, timeout=10)) as connection:
            connection.row_factory = sqlite3.Row
            rows = connection.execute(
                """
                SELECT * FROM account_delivery_attempts
                WHERE role_id = ? ORDER BY created_at, attempt_id
                """,
                (role_id,),
            ).fetchall()
        return [self._from_row(row) for row in rows]
