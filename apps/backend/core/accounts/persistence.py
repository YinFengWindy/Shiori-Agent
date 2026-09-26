"""Atomic storage and uniqueness validation for host-owned account snapshots."""

from __future__ import annotations

from dataclasses import asdict, replace
from pathlib import Path
from typing import Callable

from infra.persistence.json_store import atomic_save_json, load_json

from .models import AccountRecord, AccountResponseRules, GroupResponseRule


def ensure_unique(records: dict[str, AccountRecord]) -> None:
    """Rejects duplicate physical identities or plugin configuration references."""
    identities = {(row.platform, row.platform_account_id) for row in records.values()}
    refs = {(row.plugin_id, row.config_ref) for row in records.values()}
    if len(identities) != len(records) or len(refs) != len(records):
        raise ValueError("Duplicate account identity or configuration reference")


def load_accounts(
    path: Path, role_exists: Callable[[str], bool]
) -> dict[str, AccountRecord]:
    """Loads snapshots and durably clears owners removed before a prior crash."""
    rows = load_json(path, default=[], domain="accounts")
    if not isinstance(rows, list):
        raise ValueError("accounts.json must contain a list")
    records: dict[str, AccountRecord] = {}
    stale_owner = False
    for raw in rows:
        if "response_rules" in raw:
            rules = raw["response_rules"]
            raw = {
                **raw,
                "response_rules": AccountResponseRules(
                    private_enabled=rules.get("private_enabled", True),
                    group_enabled=rules["group_enabled"],
                    require_mention=rules["require_mention"],
                    blocked_sender_ids=tuple(rules["blocked_sender_ids"]),
                    group_rules=tuple(
                        GroupResponseRule(
                            chat_id=item["chat_id"],
                            enabled=item["enabled"],
                            require_mention=item["require_mention"],
                            blocked_sender_ids=tuple(item["blocked_sender_ids"]),
                        )
                        for item in rules.get("group_rules", [])
                    ),
                ),
            }
        row = AccountRecord(**raw)
        if row.id in records:
            raise ValueError("Duplicate account ID")
        if row.role_id is not None and not role_exists(row.role_id):
            row = replace(
                row, role_id=None, ownership_version=row.ownership_version + 1
            )
            stale_owner = True
        records[row.id] = row
    ensure_unique(records)
    if stale_owner:
        save_accounts(path, records)
    return records


def save_accounts(path: Path, records: dict[str, AccountRecord]) -> None:
    """Atomically saves public account metadata, never live reports or secrets."""
    atomic_save_json(path, [asdict(row) for row in records.values()])
