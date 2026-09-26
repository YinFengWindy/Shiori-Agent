"""Private, per-account external NapCat connection settings."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path
from uuid import uuid4

from agent.plugin_host.plugin_data import plugin_data_dir
from infra.persistence.json_store import atomic_save_json


@dataclass(frozen=True)
class QQPendingConnection:
    """Saved replacement credentials that have not passed QQ identity checks."""

    ws_uri: str
    ws_token: str
    timeout_seconds: float


@dataclass(frozen=True)
class QQConnectionConfig:
    """A stable private reference and the QQ identity verified on first login."""

    ref: str
    ws_uri: str
    ws_token: str
    expected_uin: str = ""
    display_name: str = ""
    timeout_seconds: float = 5.0
    auto_connect: bool = True
    verified: bool = False
    pending: QQPendingConnection | None = None

    def public_dict(self) -> dict[str, str | float | bool]:
        """Projects editable settings without exposing the access token."""
        editable = self.pending or self
        return {
            "ref": self.ref,
            "ws_uri": editable.ws_uri,
            "expected_uin": self.expected_uin,
            "display_name": self.display_name,
            "timeout_seconds": editable.timeout_seconds,
            "has_token": bool(editable.ws_token),
            "auto_connect": self.auto_connect,
            "verified": self.verified,
            "pending": self.pending is not None,
        }


class QQAccountsStore:
    """Persists QQ credentials under the workspace, independently of plugin code."""

    def __init__(self, workspace: Path) -> None:
        self.path = plugin_data_dir(workspace, "qq") / "accounts.json"

    def load(self) -> dict[str, QQConnectionConfig]:
        """Loads saved references; malformed private data fails visibly."""
        if not self.path.exists():
            return {}
        document = json.loads(self.path.read_text(encoding="utf-8"))
        if document.get("version") != 1 or not isinstance(
            document.get("accounts"), list
        ):
            raise ValueError("QQ 账号配置格式无效")
        accounts = []
        for row in document["accounts"]:
            if not isinstance(row, dict):
                raise ValueError("QQ 账号配置条目无效")
            pending = row.get("pending")
            if pending is not None and not isinstance(pending, dict):
                raise ValueError("QQ 待连接配置无效")
            accounts.append(
                QQConnectionConfig(
                    **{
                        **row,
                        "pending": (
                            QQPendingConnection(**pending)
                            if isinstance(pending, dict)
                            else None
                        ),
                    }
                )
            )
        if len({row.ref for row in accounts}) != len(accounts):
            raise ValueError("QQ 账号配置引用重复")
        return {row.ref: row for row in accounts}

    def save(self, accounts: dict[str, QQConnectionConfig]) -> None:
        """Atomically replaces plugin-private connection settings."""
        self.path.parent.mkdir(parents=True, exist_ok=True)
        atomic_save_json(
            self.path,
            {"version": 1, "accounts": [asdict(row) for row in accounts.values()]},
        )

    def migrate_legacy(
        self,
        *,
        bot_uin: str,
        ws_uri: str,
        ws_token: str,
        timeout_seconds: float,
    ) -> dict[str, QQConnectionConfig]:
        """Copies the old single connection exactly once into a stable reference."""
        accounts = self.load()
        if (
            not bot_uin
            or "legacy" in accounts
            or any(row.expected_uin == bot_uin for row in accounts.values())
        ):
            return accounts
        accounts["legacy"] = QQConnectionConfig(
            ref="legacy",
            ws_uri=ws_uri or "ws://localhost:3001",
            ws_token=ws_token,
            expected_uin=bot_uin,
            timeout_seconds=timeout_seconds,
        )
        self.save(accounts)
        return accounts

    @staticmethod
    def new_ref() -> str:
        """Creates an opaque reference with no credential or QQ number in it."""
        return uuid4().hex
