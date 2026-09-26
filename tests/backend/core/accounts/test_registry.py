"""Account identity and ownership survive plugin and role lifecycle changes."""

from __future__ import annotations

import pytest

from core.accounts import AccountRegistry
from core.roles.store import RoleStore
from shiori_plugin_testkit.legacy_roles import seed_legacy_bindings


def test_independent_accounts_ownership_and_recovery(tmp_path):
    roles = {"r1", "r2"}
    registry = AccountRegistry(tmp_path, roles.__contains__)
    registry.set_plugin_enabled("chat", True)
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
    registry.set_plugin_enabled("chat", False)
    assert not registry.validate_access(access)
    with pytest.raises(PermissionError):
        registry.authorize(first.record.id, "r1")
    registry.set_plugin_enabled("chat", True)

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


def test_legacy_bindings_migrate_one_account_with_group_rules_once(tmp_path):
    store = RoleStore(tmp_path)
    store.create_role(role_id="mira", name="Mira", system_prompt="Mira")
    role = store.get_role("mira")
    assert role is not None
    seed_legacy_bindings(
        tmp_path,
        role.id,
        [
            {
                "channel": "qq",
                "chat_id": "gqq:42",
                "chat_type": "group",
                "blocked_senders": ["bad"],
            }
        ],
    )
    account = store.accounts.register(
        plugin_id="qq",
        platform="qq",
        platform_account_id="100",
        config_ref="legacy",
        token="first",
    )
    row = account.record
    assert row.role_id == "mira"
    assert row.response_rules.group_enabled is False
    assert row.response_rules.group_rules[0].chat_id == "gqq:42"
    assert row.response_rules.group_rules[0].require_mention is False
    assert row.response_rules.group_rules[0].blocked_sender_ids == ("bad",)
    assert row.legacy_owner_candidates == ()
    version = row.ownership_version

    restored = RoleStore(tmp_path)
    restored.accounts.migrate_legacy_bindings()
    again = restored.accounts.get(row.id).record
    assert again.ownership_version == version
    assert again.response_rules == row.response_rules
    assert restored.get_role("mira").channel_bindings == []
    second = restored.accounts.register(
        plugin_id="qq",
        platform="qq",
        platform_account_id="200",
        config_ref="new",
        token="second",
    ).record
    assert second.role_id is None
    assert second.response_rules.group_rules == ()


def test_conflicting_legacy_owners_require_explicit_assignment(tmp_path):
    store = RoleStore(tmp_path)
    for role_id, chat_id in (("mira", "gqq:42"), ("other", "gqq:43")):
        store.create_role(role_id=role_id, name=role_id, system_prompt=role_id)
        seed_legacy_bindings(
            tmp_path,
            role_id,
            [
                {
                    "channel": "qq",
                    "chat_id": chat_id,
                    "chat_type": "group",
                    "blocked_senders": [],
                }
            ],
        )
    row = store.accounts.register(
        plugin_id="qq",
        platform="qq",
        platform_account_id="100",
        config_ref="legacy",
        token="first",
    ).record
    assert row.role_id is None
    assert row.legacy_owner_candidates == ("mira", "other")
    assert row.response_rules.group_rules == ()
    with pytest.raises(PermissionError):
        store.accounts.authorize(row.id, "mira")

    restarted = RoleStore(tmp_path)
    assert restarted.accounts.get(row.id).record.legacy_owner_candidates == (
        "mira",
        "other",
    )
    assert all(not role.channel_bindings for role in restarted.list_roles())
    assigned = restarted.accounts.assign(row.id, "other").record
    assert assigned.role_id == "other"
    assert assigned.legacy_owner_candidates == ()
    assert {rule.chat_id for rule in assigned.response_rules.group_rules} == {
        "gqq:43",
    }
    restarted.accounts.migrate_legacy_bindings()
    assert restarted.accounts.get(row.id).record == assigned


def test_multi_account_legacy_conflict_keeps_rules_for_chosen_owner(tmp_path):
    store = RoleStore(tmp_path)
    for role_id, chat_id in (("mira", "gqq:42"), ("other", "gqq:43")):
        store.create_role(role_id=role_id, name=role_id, system_prompt=role_id)
        seed_legacy_bindings(
            tmp_path,
            role_id,
            [
                {
                    "channel": "qq",
                    "chat_id": chat_id,
                    "chat_type": "group",
                    "blocked_senders": [role_id],
                }
            ],
        )
    for uin in ("100", "200"):
        store.accounts.register(
            plugin_id="qq",
            platform="qq",
            platform_account_id=uin,
            config_ref=uin,
            token=uin,
            generation="prepared",
        )
    store.accounts.publish_generation("prepared")
    rows = store.accounts.list()
    assert all(row.record.role_id is None for row in rows)
    assert all(row.record.response_rules.group_rules == () for row in rows)
    assert all(not role.channel_bindings for role in store.list_roles())

    restarted = RoleStore(tmp_path)
    chosen = restarted.accounts.assign(rows[0].record.id, "other").record
    assert [rule.chat_id for rule in chosen.response_rules.group_rules] == ["gqq:43"]
    assert chosen.response_rules.group_rules[0].blocked_sender_ids == ("other",)
    assert chosen.response_rules.group_rules[0].require_mention is False
    assert restarted.accounts.get(rows[1].record.id).record.role_id is None


def test_existing_account_owner_keeps_assignment_and_imports_its_rules(tmp_path):
    store = RoleStore(tmp_path)
    for role_id, chat_id in (("mira", "gqq:42"), ("other", "gqq:43")):
        store.create_role(role_id=role_id, name=role_id, system_prompt=role_id)
        seed_legacy_bindings(
            tmp_path,
            role_id,
            [
                {
                    "channel": "qq",
                    "chat_id": chat_id,
                    "chat_type": "group",
                    "blocked_senders": [],
                }
            ],
        )
    old_registry = AccountRegistry(
        tmp_path, lambda role_id: role_id in {"mira", "other"}
    )
    account = old_registry.register(
        plugin_id="qq",
        platform="qq",
        platform_account_id="100",
        config_ref="legacy",
        token="live",
    )
    old_registry.assign(account.record.id, "mira")
    upgraded = RoleStore(tmp_path)
    upgraded.accounts.migrate_legacy_bindings()
    row = upgraded.accounts.get(account.record.id).record
    assert row.role_id == "mira"
    assert [rule.chat_id for rule in row.response_rules.group_rules] == ["gqq:42"]


def test_account_save_before_binding_retirement_recovers_on_restart(
    tmp_path, monkeypatch
):
    store = RoleStore(tmp_path)
    store.create_role(role_id="mira", name="Mira", system_prompt="Mira")
    seed_legacy_bindings(
        tmp_path,
        "mira",
        [
            {
                "channel": "qq",
                "chat_id": "gqq:42",
                "chat_type": "group",
                "blocked_senders": [],
            }
        ],
    )

    def fail_retirement(_platforms):
        raise OSError("interrupted after account save")

    monkeypatch.setattr(store.accounts, "_retire_legacy_bindings", fail_retirement)
    with pytest.raises(OSError, match="interrupted"):
        store.accounts.register(
            plugin_id="qq",
            platform="qq",
            platform_account_id="100",
            config_ref="legacy",
            token="live",
        )
    assert store.get_role("mira").channel_bindings

    restarted = RoleStore(tmp_path)
    restarted.accounts.migrate_legacy_bindings()
    row = restarted.accounts.list()[0].record
    assert row.role_id == "mira"
    assert row.response_rules.group_rules[0].chat_id == "gqq:42"
    assert restarted.get_role("mira").channel_bindings == []


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
    registry.report(
        existing.record.id,
        "published",
        generation="next",
        connection="online",
        capabilities=frozenset({"groups"}),
    )
    assert registry.get(existing.record.id).record.known_capabilities == ()
    registry.publish_generation("next")
    assert registry.get(existing.record.id).record.display_name == "Updated"
    assert registry.get(existing.record.id).record.role_id == "role"
    assert registry.get(existing.record.id).record.known_capabilities == ("groups",)
    assert len(registry.list()) == 2
    assert {
        row.record.platform_account_id
        for row in AccountRegistry(tmp_path, lambda _role_id: True).list()
    } == {"101", "102"}


def test_known_capabilities_survive_stop_disable_and_reload(tmp_path):
    registry = AccountRegistry(tmp_path, lambda _role_id: True)
    registry.set_plugin_enabled("chat", True)
    account = registry.register(
        plugin_id="chat",
        platform="chat",
        platform_account_id="101",
        config_ref="one",
        token="running",
    )
    registry.report(
        account.record.id,
        "running",
        connection="online",
        capabilities=frozenset({"groups", "contacts"}),
    )
    registry.assign(account.record.id, "role")
    assert registry.validate_access(registry.authorize(account.record.id, "role"))
    registry.unregister(account.record.id, "running")
    registry.set_plugin_enabled("chat", False)
    stopped = registry.get(account.record.id)
    assert not stopped.plugin_enabled
    assert stopped.capabilities == frozenset()
    assert stopped.record.known_capabilities == ("contacts", "groups")
    with pytest.raises(PermissionError):
        registry.authorize(account.record.id, "role")
    restored = AccountRegistry(tmp_path, lambda _role_id: True)
    assert restored.get(account.record.id).record.known_capabilities == (
        "contacts",
        "groups",
    )


def test_identity_snapshot_distinguishes_omitted_and_explicit_empty(tmp_path):
    registry = AccountRegistry(tmp_path, lambda _role_id: True)
    identity = dict(
        plugin_id="chat",
        platform="chat",
        platform_account_id="101",
        config_ref="one",
        token="running",
    )
    created = registry.register(
        **identity, display_name="Display name", avatar_url="https://example.test/a.png"
    )
    preserved = registry.register(**identity)
    assert preserved.record.display_name == "Display name"
    assert preserved.record.avatar_url == "https://example.test/a.png"

    cleared = registry.register(**identity, display_name="", avatar_url="")
    assert cleared.record.id == created.record.id
    assert cleared.record.display_name == ""
    assert cleared.record.avatar_url == ""
    restored = AccountRegistry(tmp_path, lambda _role_id: True)
    assert restored.get(created.record.id).record.display_name == ""
    assert restored.get(created.record.id).record.avatar_url == ""
