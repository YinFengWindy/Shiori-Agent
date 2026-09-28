"""The one JSON shape of account response rules, for bridge payloads and plugin storage."""

from __future__ import annotations

from typing import Any

from .models import AccountResponseRules, GroupResponseRule


def _ids(value: Any, error: str) -> tuple[str, ...]:
    if not isinstance(value, list) or any(
        not isinstance(item, str) or not item.strip() for item in value
    ):
        raise ValueError(error)
    return tuple(dict.fromkeys(item.strip() for item in value))


def response_rules_from_dict(value: Any) -> AccountResponseRules:
    """Parses rules strictly; malformed fields raise before anything is saved."""
    if not isinstance(value, dict):
        raise ValueError("response_rules must be an object")
    if any(
        type(value.get(field)) is not bool
        for field in ("private_enabled", "group_enabled", "require_mention")
    ):
        raise ValueError("Invalid account response rules")
    blocked = _ids(value.get("blocked_sender_ids"), "Invalid account response rules")
    raw_groups = value.get("group_rules")
    if not isinstance(raw_groups, list):
        raise ValueError("Invalid account response rules")
    groups: list[GroupResponseRule] = []
    for raw in raw_groups:
        if not isinstance(raw, dict):
            raise ValueError("Invalid group response rule")
        chat_id = raw.get("chat_id")
        if (
            not isinstance(chat_id, str)
            or not chat_id.strip()
            or type(raw.get("enabled")) is not bool
            or type(raw.get("require_mention")) is not bool
        ):
            raise ValueError("Invalid group response rule")
        groups.append(
            GroupResponseRule(
                chat_id=chat_id.strip(),
                enabled=raw["enabled"],
                require_mention=raw["require_mention"],
                blocked_sender_ids=_ids(
                    raw.get("blocked_sender_ids"), "Invalid group response rule"
                ),
            )
        )
    if len({group.chat_id for group in groups}) != len(groups):
        raise ValueError("Duplicate group response rule")
    return AccountResponseRules(
        private_enabled=value["private_enabled"],
        group_enabled=value["group_enabled"],
        require_mention=value["require_mention"],
        blocked_sender_ids=blocked,
        group_rules=tuple(groups),
    )


def stored_response_rules(value: Any) -> AccountResponseRules | None:
    """Reads rules a plugin saved with an account; None when it saved none yet."""
    return None if value is None else response_rules_from_dict(value)


def response_rules_to_dict(rules: AccountResponseRules) -> dict[str, Any]:
    """The JSON form ``response_rules_from_dict`` reads back unchanged."""
    return {
        "private_enabled": rules.private_enabled,
        "group_enabled": rules.group_enabled,
        "require_mention": rules.require_mention,
        "blocked_sender_ids": list(rules.blocked_sender_ids),
        "group_rules": [
            {
                "chat_id": rule.chat_id,
                "enabled": rule.enabled,
                "require_mention": rule.require_mention,
                "blocked_sender_ids": list(rule.blocked_sender_ids),
            }
            for rule in rules.group_rules
        ],
    }
