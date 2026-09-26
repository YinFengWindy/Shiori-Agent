"""Bridge read and ownership commands for host-owned account records."""

from __future__ import annotations

from typing import Any

from core.accounts import AccountRegistry, AccountSnapshot

from .account_rule_payload import parse_response_rules


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
        "legacy_owner_candidates": list(row.legacy_owner_candidates),
        "plugin_enabled": snapshot.plugin_enabled,
        "runtime_active": snapshot.runtime_active,
        "connection": snapshot.connection,
        "capabilities": sorted(snapshot.capabilities),
        "known_capabilities": list(row.known_capabilities),
        "error": snapshot.error,
        "response_rules": {
            "private_enabled": row.response_rules.private_enabled,
            "group_enabled": row.response_rules.group_enabled,
            "require_mention": row.response_rules.require_mention,
            "blocked_sender_ids": list(row.response_rules.blocked_sender_ids),
            "group_rules": [
                {
                    "chat_id": rule.chat_id,
                    "enabled": rule.enabled,
                    "require_mention": rule.require_mention,
                    "blocked_sender_ids": list(rule.blocked_sender_ids),
                }
                for rule in row.response_rules.group_rules
            ],
        },
    }


class DesktopAccountRequestHandler:
    """Exposes the canonical account registry to the desktop bridge."""

    def __init__(self, accounts: AccountRegistry) -> None:
        self._accounts = accounts

    async def handle(
        self, method: str, payload: dict[str, Any]
    ) -> dict[str, Any] | None:
        """Handles account listing, detail, and exclusive role assignment."""
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
        if method == "accounts.assign":
            role_id = str(payload.get("role_id") or "").strip() or None
            return {
                "account": _serialize(
                    self._accounts.assign(str(payload["account_id"]), role_id)
                )
            }
        if method == "accounts.rules.set":
            rules = parse_response_rules(payload["response_rules"])
            return {
                "account": _serialize(
                    self._accounts.set_response_rules(str(payload["account_id"]), rules)
                )
            }
        return None
