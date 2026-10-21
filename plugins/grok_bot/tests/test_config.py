import pytest
from plugins.grok_bot.backend.config import read_connection


def test_legacy_verification_and_hidden_filters_migrate_without_revoking_tools(config):
    saved = {
        **config.model_dump(),
        "verified": False,
        "response_rules": {
            "private_enabled": False,
            "group_enabled": False,
            "blocked_sender_ids": [config.peer_id],
            "allow_full_tools": True,
        },
    }
    migrated = read_connection(saved)
    assert "verified" not in migrated.model_dump()
    assert migrated.response_rules == {
        "private_enabled": True,
        "group_enabled": False,
        "blocked_sender_ids": [],
        "allow_full_tools": True,
    }
    assert migrated.connection_id == config.connection_id
    assert migrated.peer_id == config.peer_id
    assert migrated.callback_token == config.callback_token
    assert read_connection(migrated.model_dump()) == migrated


def test_migration_does_not_ignore_unknown_fields_or_enable_missing_tool_grants(config):
    migrated = read_connection(config.model_dump())
    assert not migrated.response_rules.get("allow_full_tools", False)
    with pytest.raises(ValueError, match="unexpected"):
        read_connection({**config.model_dump(), "unexpected": "secret"})
