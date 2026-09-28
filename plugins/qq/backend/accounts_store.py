"""Plugin-private managed NapCat account records."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Literal
from uuid import uuid4

from agent.plugin_host.plugin_data import plugin_data_dir
from core.accounts import (
    AccountResponseRules,
    ViaAccount,
    response_rules_to_dict,
    stored_response_rules,
)
from infra.persistence.json_store import atomic_save_json


@dataclass(frozen=True)
class QQConnectionConfig:
    """A managed instance and the QQ identity verified on first login."""

    ref: str
    ws_uri: str
    ws_token: str
    expected_uin: str = ""
    display_name: str = ""
    # The QQ avatar as an image data URI, refreshed on each connect; "" if unknown.
    avatar: str = ""
    timeout_seconds: float = 5.0
    auto_connect: bool = True
    verified: bool = False
    mode: Literal["managed"] = "managed"
    # Owner of the temporary login and eventual verified account.
    role_id: str | None = None
    # Response rules edited on the host; None until first saved (defaults).
    response_rules: AccountResponseRules | None = None

    def via_account(self) -> dict[str, str]:
        """The account snapshot the host stores with each message it passes.

        QQ names an account by its QQ number; the nickname is the one seen at
        the last login.
        """
        name = self.display_name.strip()
        uin = self.expected_uin
        return ViaAccount(
            platform="qq",
            platform_account_id=uin,
            display_name=name,
            prefix=f"QQ 号「{name}」（{uin}）" if name else f"QQ 号 {uin}",
        ).to_metadata()

    def public_dict(self) -> dict[str, str | float | bool | None]:
        """Projects account identity and state without internal socket secrets."""
        return {
            "ref": self.ref,
            "expected_uin": self.expected_uin,
            "display_name": self.display_name,
            "auto_connect": self.auto_connect,
            "verified": self.verified,
            "mode": self.mode,
            "role_id": self.role_id,
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
        if (
            not isinstance(document, dict)
            or document.get("version") != 1
            or not isinstance(document.get("accounts"), list)
        ):
            raise ValueError("QQ 账号配置格式无效")
        accounts = []
        for row in document["accounts"]:
            if not isinstance(row, dict):
                raise ValueError("QQ 账号配置条目无效")
            if row.get("mode") != "managed":
                raise ValueError("QQ 账号配置格式无效")
            accounts.append(
                QQConnectionConfig(
                    **{
                        **row,
                        "response_rules": stored_response_rules(
                            row.get("response_rules")
                        ),
                    }
                )
            )
        if len({row.ref for row in accounts}) != len(accounts):
            raise ValueError("QQ 账号配置引用重复")
        return {row.ref: row for row in accounts}

    def save(self, accounts: dict[str, QQConnectionConfig]) -> None:
        """Persists only identities verified by QQ; temporary logins stay in memory."""
        self.path.parent.mkdir(parents=True, exist_ok=True)
        atomic_save_json(
            self.path,
            {
                "version": 1,
                "accounts": [
                    _row(config) for config in accounts.values() if config.verified
                ],
            },
        )

    @staticmethod
    def new_ref() -> str:
        """Creates an opaque reference with no credential or QQ number in it."""
        return uuid4().hex


def _row(config: QQConnectionConfig) -> dict[str, Any]:
    """The JSON row of one config; rules use the shared response-rule shape."""
    return {
        **asdict(config),
        "response_rules": (
            response_rules_to_dict(config.response_rules)
            if config.response_rules is not None
            else None
        ),
    }
