"""Account identity and ownership survive plugin and role lifecycle changes."""

from __future__ import annotations

import pytest

from core.accounts import (
    AccountDeletingError,
    AccountDeletionPlan,
    AccountNotFoundError,
    AccountRegistry,
)
from core.accounts.models import AccountResponseRules
from core.roles.store import RoleStore
from shiori_plugin_testkit.legacy_roles import seed_legacy_bindings


def test_independent_accounts_ownership_and_recovery(tmp_path):
    roles = {"r1", "r2", "r3"}
    registry = AccountRegistry(tmp_path, roles.__contains__)
    registry.set_plugin_enabled("chat", True)
    first = registry.register(
        plugin_id="chat",
        platform="chat",
        platform_account_id="101",
        config_ref="one",
        token="generation-1",
        role_id="r1",
        display_name="First",
    )
    second = registry.register(
        plugin_id="chat",
        platform="chat",
        platform_account_id="102",
        config_ref="two",
        token="generation-1",
        role_id="r2",
        display_name="Second",
    )
    assert first.record.id != second.record.id
    assert (first.record.role_id, second.record.role_id) == ("r1", "r2")
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

    with pytest.raises(ValueError, match="另一个插件"):
        registry.register(
            plugin_id="other",
            platform="chat",
            platform_account_id="101",
            config_ref="duplicate",
            token="generation-2",
            role_id="r1",
        )
    with pytest.raises(ValueError, match="配置引用已属于"):
        registry.register(
            plugin_id="chat",
            platform="chat",
            platform_account_id="103",
            config_ref="one",
            token="generation-1",
            role_id="r3",
        )
    with pytest.raises(ValueError, match="已作为另一个账号添加"):
        registry.register(
            plugin_id="chat",
            platform="chat",
            platform_account_id="101",
            config_ref="duplicate",
            token="generation-1",
            role_id="r1",
        )
    with pytest.raises(PermissionError):
        registry.authorize(first.record.id, "r2")

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
    assert restored.get(first.record.id).record.role_id == "r1"


def test_registration_requires_one_owner_role_per_plugin_and_identity(tmp_path):
    registry = AccountRegistry(tmp_path, {"r1", "r2"}.__contains__)
    identity = dict(plugin_id="chat", platform="chat", token="live")
    for role_id, error in (("", "没有所属角色"), ("missing", "角色不存在")):
        with pytest.raises(ValueError, match=error):
            registry.register(
                **identity,
                platform_account_id="101",
                config_ref="one",
                role_id=role_id,
            )
    owned = registry.register(
        **identity, platform_account_id="101", config_ref="one", role_id="r1"
    )
    # A second account of the same plugin for the same role is refused.
    with pytest.raises(ValueError, match="已有账号"):
        registry.register(
            **identity, platform_account_id="102", config_ref="two", role_id="r1"
        )
    # Another plugin, or another role, may still add its own account.
    registry.register(
        plugin_id="mail",
        platform="mail",
        platform_account_id="101",
        config_ref="one",
        token="live",
        role_id="r1",
    )
    registry.register(
        **identity, platform_account_id="102", config_ref="two", role_id="r2"
    )
    # The same platform account cannot be registered for a second role.
    with pytest.raises(ValueError, match="另一个角色"):
        registry.register(
            **identity, platform_account_id="101", config_ref="one", role_id="r2"
        )
    again = registry.register(
        **identity, platform_account_id="101", config_ref="one", role_id="r1"
    )
    assert again.record.id == owned.record.id
    assert len(registry.list(role_id="r1")) == 2


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
        role_id="mira",
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
    restored.create_role(role_id="other", name="Other", system_prompt="Other")
    second = restored.accounts.register(
        plugin_id="qq",
        platform="qq",
        platform_account_id="200",
        config_ref="new",
        token="second",
        role_id="other",
    ).record
    assert second.role_id == "other"
    assert second.response_rules.group_rules == ()


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
            role_id="mira",
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
        role_id="role",
    )
    account_id = account.record.id
    registry.report(account_id, "old", connection="online")
    access = registry.authorize(account_id, "role")
    replacement = registry.register(
        plugin_id="chat",
        platform="chat",
        platform_account_id="101",
        config_ref="one",
        token="new",
        role_id="role",
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
            role_id="role",
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
        role_id="role",
    )
    registry.unregister(account.record.id, "old")
    registry.register(
        plugin_id="chat",
        platform="chat",
        platform_account_id="101",
        config_ref="one",
        token="new",
        role_id="role",
    )
    with pytest.raises(RuntimeError, match="superseded"):
        registry.register(
            plugin_id="chat",
            platform="chat",
            platform_account_id="101",
            config_ref="one",
            token="old",
            role_id="role",
        )


def test_candidate_identity_is_hidden_until_published_or_discarded(tmp_path):
    registry = AccountRegistry(tmp_path, {"role", "other"}.__contains__)
    existing = registry.register(
        plugin_id="chat",
        platform="chat",
        platform_account_id="101",
        config_ref="one",
        token="old",
        role_id="role",
        display_name="Original",
    )
    registry.register(
        plugin_id="chat",
        platform="chat",
        platform_account_id="101",
        config_ref="one",
        token="prepared",
        role_id="role",
        generation="discarded",
        display_name="Uncommitted",
    )
    registry.register(
        plugin_id="chat",
        platform="chat",
        platform_account_id="102",
        config_ref="two",
        token="prepared",
        role_id="other",
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
        role_id="role",
        generation="next",
        display_name="Updated",
    )
    registry.register(
        plugin_id="chat",
        platform="chat",
        platform_account_id="102",
        config_ref="two",
        token="published",
        role_id="other",
        generation="next",
    )
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
        role_id="role",
    )
    registry.report(
        account.record.id,
        "running",
        connection="online",
        capabilities=frozenset({"groups", "contacts"}),
    )
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
        role_id="role",
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


def _owned_account(tmp_path, roles=frozenset({"r1", "r2"})):
    registry = AccountRegistry(tmp_path, roles.__contains__)
    registry.set_plugin_enabled("chat", True)
    account = registry.register(
        plugin_id="chat",
        platform="chat",
        platform_account_id="101",
        config_ref="one",
        token="generation-1",
        role_id="r1",
    )
    registry.report(account.record.id, "generation-1", connection="online")
    return registry, account.record.id


class _Deletion:
    """Scripted plugin plan and host config writer recording every step."""

    def __init__(self, config=None, fail=()):
        self.config = config
        self.fail = set(fail)
        self.steps: list[str] = []

    def _step(self, name):
        self.steps.append(name)
        if name in self.fail:
            self.fail.discard(name)
            raise OSError(f"{name} failed")

    def plan(self, config_ref):
        assert config_ref == "one"
        self._step("plan")

        async def disconnect():
            self._step("disconnect")

        async def purge():
            self._step("purge")

        return AccountDeletionPlan(disconnect, purge, self.config)

    def check(self, plugin_id, values):
        assert (plugin_id, values) == ("chat", self.config)
        self._step("check")

    async def write(self, plugin_id, values):
        assert (plugin_id, values) == ("chat", self.config)
        self._step("write")

    async def run(self, registry, account_id, role_id="r1"):
        await registry.delete(
            account_id,
            role_id=role_id,
            check_plugin_config=self.check,
            write_plugin_config=self.write,
        )


@pytest.mark.asyncio
async def test_delete_validates_disconnects_writes_purges_then_forgets(tmp_path):
    registry, account_id = _owned_account(tmp_path)
    deletion = _Deletion(config={"bots": []})
    registry.set_delete_handler("chat", deletion.plan)

    await deletion.run(registry, account_id)

    assert deletion.steps == ["plan", "check", "disconnect", "purge", "write"]
    assert registry.list() == []
    with pytest.raises(KeyError):
        registry.get(account_id)
    with pytest.raises(RuntimeError, match="no longer active"):
        registry.report(account_id, "generation-1", connection="offline")
    assert AccountRegistry(tmp_path, {"r1"}.__contains__).list() == []
    with pytest.raises(AccountNotFoundError):
        await deletion.run(registry, account_id)


@pytest.mark.asyncio
async def test_invalid_plugin_config_aborts_before_anything_is_purged(tmp_path):
    registry, account_id = _owned_account(tmp_path)
    deletion = _Deletion(config={"bots": "invalid"}, fail={"check"})
    registry.set_delete_handler("chat", deletion.plan)

    with pytest.raises(OSError, match="check failed"):
        await deletion.run(registry, account_id)

    assert deletion.steps == ["plan", "check"]
    assert registry.get(account_id).connection == "online"
    restarted = AccountRegistry(tmp_path, {"r1"}.__contains__)
    assert [row.record.id for row in restarted.list()] == [account_id]
    # The deletion fence is released after a failure.
    registry.set_response_rules(account_id, AccountResponseRules(group_enabled=False))


@pytest.mark.asyncio
@pytest.mark.parametrize("failing", ["write", "purge"])
async def test_failed_write_or_purge_keeps_record_and_retry_completes(
    tmp_path, failing
):
    registry, account_id = _owned_account(tmp_path)
    deletion = _Deletion(config={}, fail={failing})
    registry.set_delete_handler("chat", deletion.plan)

    with pytest.raises(OSError, match=f"{failing} failed"):
        await deletion.run(registry, account_id)
    completed = ["plan", "check", "disconnect", "purge", "write"]
    assert deletion.steps == completed[: completed.index(failing) + 1]
    restarted = AccountRegistry(tmp_path, {"r1"}.__contains__)
    assert [row.record.id for row in restarted.list()] == [account_id]

    await deletion.run(registry, account_id)
    assert registry.list() == []


@pytest.mark.asyncio
async def test_account_is_frozen_and_cannot_be_revived_while_deleting(tmp_path):
    registry, account_id = _owned_account(tmp_path)
    refused: list[str] = []

    def plan(config_ref):
        async def disconnect():
            for change in (
                lambda: registry.set_response_rules(
                    account_id, AccountResponseRules(group_enabled=False)
                ),
                # A newly prepared generation re-registering the identity.
                lambda: registry.register(
                    plugin_id="chat",
                    platform="chat",
                    platform_account_id="101",
                    config_ref="one",
                    token="generation-2",
                    role_id="r1",
                    generation="g2",
                ),
            ):
                with pytest.raises(AccountDeletingError, match="正在删除") as error:
                    change()
                refused.append(str(error.value))
            # A retiring channel's final report is ignored, not applied.
            ignored = registry.report(
                account_id, "generation-1", connection="error", error="late"
            )
            assert ignored.connection == "online"

        async def purge():
            return None

        return AccountDeletionPlan(disconnect, purge)

    registry.set_delete_handler("chat", plan)
    await registry.delete(
        account_id,
        role_id="r1",
        check_plugin_config=lambda *_: None,
        write_plugin_config=_Deletion().write,
    )
    assert refused == ["账号正在删除"] * 2
    assert registry.list() == []
    # After deletion a stale report cannot bring the record back either.
    with pytest.raises(RuntimeError, match="no longer active"):
        registry.report(
            account_id,
            "generation-1",
            connection="online",
            capabilities=frozenset({"send"}),
        )
    assert registry.list() == []
    assert AccountRegistry(tmp_path, {"r1"}.__contains__).list() == []


@pytest.mark.asyncio
async def test_delete_is_refused_when_plugin_cannot_clean_up_or_role_differs(
    tmp_path,
):
    registry, account_id = _owned_account(tmp_path)
    deletion = _Deletion()

    with pytest.raises(RuntimeError, match="未启用或未加载"):
        await deletion.run(registry, account_id)
    plan = deletion.plan
    registry.set_delete_handler("chat", plan)
    with pytest.raises(PermissionError, match="不属于"):
        await deletion.run(registry, account_id, role_id="r2")
    registry.set_plugin_enabled("chat", False)
    with pytest.raises(RuntimeError, match="未启用或未加载"):
        await deletion.run(registry, account_id)
    registry.clear_delete_handler("chat", plan)
    registry.set_plugin_enabled("chat", True)
    with pytest.raises(RuntimeError, match="未启用或未加载"):
        await deletion.run(registry, account_id)
    assert deletion.steps == []
    assert registry.get(account_id).record.role_id == "r1"


def test_config_write_keeps_owners_and_refuses_unusable_entries(tmp_path):
    from core.accounts import ConfiguredAccount

    registry = AccountRegistry(tmp_path, {"r1", "r2"}.__contains__)
    registry.register(
        plugin_id="chat",
        platform="chat",
        platform_account_id="101",
        config_ref="one",
        token="live",
        role_id="r1",
    )

    def read(values):
        return [
            ConfiguredAccount(ref, row.get("role"), "chat", row.get("id"))
            for ref, row in values.items()
        ]

    registry.set_config_reader("chat", read)
    saved = {"one": {"role": "r1", "id": "101"}, "old": {"role": None, "id": "9"}}
    # Unchanged entries pass, even an ownerless one left by older data.
    registry.check_config_write("chat", saved, saved)
    registry.check_config_write("chat", saved, {**saved, "two": {"role": "r2"}})
    for after, error in (
        ({**saved, "one": {"role": "r2", "id": "101"}}, "不能更改"),
        ({**saved, "old": {"role": "r2", "id": "9"}}, "不能更改"),
        ({**saved, "two": {"role": None}}, "没有所属角色"),
        ({**saved, "two": {"role": "gone"}}, "角色不存在"),
        ({**saved, "two": {"role": "r1"}}, "已有账号"),
        ({**saved, "two": {"role": "r2", "id": "101"}}, "已作为另一个账号添加"),
        ({**saved, "two": {"role": "r2"}, "three": {"role": "r2"}}, "已有账号"),
    ):
        with pytest.raises(ValueError, match=error):
            registry.check_config_write("chat", saved, after)
