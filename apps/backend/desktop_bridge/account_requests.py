"""Bridge read and ownership commands for host-owned account records."""

from __future__ import annotations

from typing import Any

from core.accounts import AccountRegistry, AccountSnapshot
from core.accounts.models import AccountResponseRules, GroupResponseRule


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
        "plugin_enabled": snapshot.plugin_enabled,
        "runtime_active": snapshot.runtime_active,
        "connection": snapshot.connection,
        "capabilities": sorted(snapshot.capabilities),
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
            raw = payload["response_rules"]
            if not isinstance(raw, dict):
                raise ValueError("response_rules must be an object")
            group_enabled = raw.get("group_enabled")
            private_enabled = raw.get("private_enabled")
            require_mention = raw.get("require_mention")
            blocked = raw.get("blocked_sender_ids")
            group_rules = raw.get("group_rules")
            if (
                type(private_enabled) is not bool
                or type(group_enabled) is not bool
                or type(require_mention) is not bool
                or not isinstance(blocked, list)
                or any(
                    not isinstance(item, str) or not item.strip() for item in blocked
                )
                or not isinstance(group_rules, list)
            ):
                raise ValueError("Invalid account response rules")
            groups = []
            for group in group_rules:
                if not isinstance(group, dict):
                    raise ValueError("Invalid group response rule")
                chat_id = group.get("chat_id")
                members = group.get("blocked_sender_ids")
                if (
                    not isinstance(chat_id, str)
                    or not chat_id.strip()
                    or type(group.get("enabled")) is not bool
                    or type(group.get("require_mention")) is not bool
                    or not isinstance(members, list)
                    or any(
                        not isinstance(item, str) or not item.strip()
                        for item in members
                    )
                ):
                    raise ValueError("Invalid group response rule")
                groups.append(
                    GroupResponseRule(
                        chat_id=chat_id.strip(),
                        enabled=group["enabled"],
                        require_mention=group["require_mention"],
                        blocked_sender_ids=tuple(
                            dict.fromkeys(item.strip() for item in members)
                        ),
                    )
                )
            if len({group.chat_id for group in groups}) != len(groups):
                raise ValueError("Duplicate group response rule")
            rules = AccountResponseRules(
                private_enabled=private_enabled,
                group_enabled=group_enabled,
                require_mention=require_mention,
                blocked_sender_ids=tuple(
                    dict.fromkeys(item.strip() for item in blocked)
                ),
                group_rules=tuple(groups),
            )
            return {
                "account": _serialize(
                    self._accounts.set_response_rules(str(payload["account_id"]), rules)
                )
            }
        return None
