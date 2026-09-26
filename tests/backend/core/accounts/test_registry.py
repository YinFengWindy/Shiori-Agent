"""Account identity and ownership survive plugin and role lifecycle changes."""

from __future__ import annotations

import pytest

from core.accounts import AccountRegistry


def test_independent_accounts_ownership_and_recovery(tmp_path):
    roles = {"r1", "r2"}
    registry = AccountRegistry(tmp_path, roles.__contains__)
    first = registry.register(
        plugin_id="chat",
        platform="chat",
        platform_account_id="101",
        config_ref="one",
        token="generation-1",
        display_name="First",
    )
    second = registry.register(
        plugin_id="chat",
        platform="chat",
        platform_account_id="102",
        config_ref="two",
        token="generation-1",
        display_name="Second",
    )
    assert first.record.id != second.record.id
    registry.assign(first.record.id, "r1")
    registry.assign(second.record.id, "r2")
    registry.report(
        first.record.id,
        "generation-1",
        connection="online",
        capabilities=frozenset({"contacts"}),
    )
    registry.report(second.record.id, "generation-1", connection="login_required")
    access = registry.authorize(first.record.id, "r1")
    assert registry.validate_access(access)

    with pytest.raises(ValueError, match="already belongs"):
        registry.register(
            plugin_id="other",
            platform="chat",
            platform_account_id="101",
            config_ref="duplicate",
            token="generation-2",
        )
    with pytest.raises(ValueError, match="Configuration reference"):
        registry.register(
            plugin_id="chat",
            platform="chat",
            platform_account_id="103",
            config_ref="one",
            token="generation-1",
        )
    with pytest.raises(ValueError, match="another configuration reference"):
        registry.register(
            plugin_id="chat",
            platform="chat",
            platform_account_id="101",
            config_ref="duplicate",
            token="generation-1",
        )
    with pytest.raises(PermissionError):
        registry.authorize(first.record.id, "r2")

    registry.assign(first.record.id, "r2")
    assert not registry.validate_access(access)
    registry.unassign_role("r2")
    assert registry.get(first.record.id).record.role_id is None
    assert registry.get(second.record.id).record.role_id is None

    restored = AccountRegistry(tmp_path, roles.__contains__)
    assert {row.record.id for row in restored.list()} == {
        first.record.id,
        second.record.id,
    }
    assert all(
        not row.plugin_enabled and row.connection == "unknown"
        for row in restored.list()
    )
    assert restored.get(first.record.id).record.display_name == "First"


def test_live_generation_fence_and_error_report(tmp_path):
    registry = AccountRegistry(tmp_path, lambda role_id: role_id == "role")
    registry.set_plugin_enabled("chat", True)
    account = registry.register(
        plugin_id="chat",
        platform="chat",
        platform_account_id="101",
        config_ref="one",
        token="old",
    )
    account_id = account.record.id
    registry.assign(account_id, "role")
    registry.report(account_id, "old", connection="online")
    access = registry.authorize(account_id, "role")
    replacement = registry.register(
        plugin_id="chat",
        platform="chat",
        platform_account_id="101",
        config_ref="one",
        token="new",
    )
    assert replacement.record.id == account_id
    assert replacement.record.role_id == "role"
    assert replacement.connection == "unknown"
    with pytest.raises(RuntimeError, match="superseded"):
        registry.register(
            plugin_id="chat",
            platform="chat",
            platform_account_id="101",
            config_ref="one",
            token="old",
        )
    registry.unregister(account_id, "old")
    assert registry.get(account_id).plugin_enabled
    assert not registry.validate_access(access)
    with pytest.raises(RuntimeError, match="no longer active"):
        registry.report(account_id, "old", connection="online")
    failed = registry.report(
        account_id, "new", connection="error", error="auth rejected"
    )
    assert failed.error == "auth rejected"
    assert failed.connection == "error"
    registry.unregister(account_id, "new")
    assert registry.get(account_id).record.role_id == "role"


def test_stopped_old_instance_cannot_reclaim_after_handover(tmp_path):
    registry = AccountRegistry(tmp_path, lambda _role_id: True)
    account = registry.register(
        plugin_id="chat",
        platform="chat",
        platform_account_id="101",
        config_ref="one",
        token="old",
    )
    registry.unregister(account.record.id, "old")
    registry.register(
        plugin_id="chat",
        platform="chat",
        platform_account_id="101",
        config_ref="one",
        token="new",
    )
    with pytest.raises(RuntimeError, match="superseded"):
        registry.register(
            plugin_id="chat",
            platform="chat",
            platform_account_id="101",
            config_ref="one",
            token="old",
        )


def test_candidate_identity_is_hidden_until_published_or_discarded(tmp_path):
    registry = AccountRegistry(tmp_path, lambda role_id: role_id == "role")
    existing = registry.register(
        plugin_id="chat",
        platform="chat",
        platform_account_id="101",
        config_ref="one",
        token="old",
        display_name="Original",
    )
    registry.register(
        plugin_id="chat",
        platform="chat",
        platform_account_id="101",
        config_ref="one",
        token="prepared",
        generation="discarded",
        display_name="Uncommitted",
    )
    registry.register(
        plugin_id="chat",
        platform="chat",
        platform_account_id="102",
        config_ref="two",
        token="prepared",
        generation="discarded",
    )
    assert registry.get(existing.record.id).record.display_name == "Original"
    assert len(registry.list()) == 1
    registry.drop_generation("discarded")
    assert len(AccountRegistry(tmp_path, lambda _role_id: True).list()) == 1

    registry.register(
        plugin_id="chat",
        platform="chat",
        platform_account_id="101",
        config_ref="one",
        token="published",
        generation="next",
        display_name="Updated",
    )
    registry.register(
        plugin_id="chat",
        platform="chat",
        platform_account_id="102",
        config_ref="two",
        token="published",
        generation="next",
    )
    registry.assign(existing.record.id, "role")
    registry.publish_generation("next")
    assert registry.get(existing.record.id).record.display_name == "Updated"
    assert registry.get(existing.record.id).record.role_id == "role"
    assert len(registry.list()) == 2
    assert {
        row.record.platform_account_id
        for row in AccountRegistry(tmp_path, lambda _role_id: True).list()
    } == {"101", "102"}
