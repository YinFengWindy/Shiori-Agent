"""Bridge commands over the account index of the loaded plugins."""

from __future__ import annotations

from typing import Any

from core.accounts import (
    AccountRegistry,
    AccountSnapshot,
    response_rules_from_dict,
    response_rules_to_dict,
)


def _serialize(snapshot: AccountSnapshot) -> dict[str, Any]:
    row = snapshot.record
    return {
        "id": row.id,
        "plugin_id": row.plugin_id,
        "platform": row.platform,
        "platform_account_id": row.platform_account_id,
        "config_ref": row.config_ref,
        "display_name": row.display_name,
        "avatar_url": row.avatar_url,
        "role_id": row.role_id,
        "runtime_active": snapshot.runtime_active,
        "connection": snapshot.connection,
        "capabilities": sorted(snapshot.capabilities),
        "error": snapshot.error,
        "response_rules": response_rules_to_dict(row.response_rules),
    }


class DesktopAccountRequestHandler:
    """Exposes the account index to the desktop bridge."""

    def __init__(self, accounts: AccountRegistry) -> None:
        self._accounts = accounts

    async def handle(
        self, method: str, payload: dict[str, Any]
    ) -> dict[str, Any] | None:
        """Handles account listing, detail, response rules, and deletion."""
        if method == "accounts.list":
            role_id = str(payload.get("role_id") or "").strip() or None
            return {
                "accounts": [
                    _serialize(account)
                    for account in self._accounts.list(role_id=role_id)
                ]
            }
        if method == "accounts.get":
            return {
                "account": _serialize(self._accounts.get(str(payload["account_id"])))
            }
        if method == "accounts.rules.set":
            rules = response_rules_from_dict(payload["response_rules"])
            return {
                "account": _serialize(
                    self._accounts.set_response_rules(str(payload["account_id"]), rules)
                )
            }
        if method == "accounts.delete":
            account_id = str(payload.get("account_id") or "").strip()
            role_id = str(payload.get("role_id") or "").strip()
            if not account_id or not role_id:
                raise ValueError("account_id 和 role_id 不能为空")
            await self._accounts.delete(account_id, role_id=role_id)
            return {"account_id": account_id}
        return None
