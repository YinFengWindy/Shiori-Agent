"""The one JSON shape of account response rules, for bridge payloads and plugin storage."""

from __future__ import annotations

from typing import Any

from .models import AccountResponseRules


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
    return AccountResponseRules(
        private_enabled=value["private_enabled"],
        group_enabled=value["group_enabled"],
        require_mention=value["require_mention"],
        blocked_sender_ids=blocked,
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
    }
