"""The account index holds only what loaded plugins register, under one ownership rule."""

from __future__ import annotations

import base64

import pytest

from core.accounts import (
    AccountDeletingError,
    AccountDeletionPlan,
    AccountNotFoundError,
    AccountRegistry,
    AccountResponseRules,
)


def _register(registry, account="101", ref="one", role="r1", **extra):
    return registry.register(
        plugin_id="chat",
        platform="chat",
        platform_account_id=account,
        config_ref=ref,
        token=extra.pop("token", "generation-1"),
        role_id=role,
        **extra,
    )


def test_account_id_is_derived_from_the_identity_and_nothing_is_persisted(tmp_path):
    registry = AccountRegistry({"r1"}.__contains__)
    account = _register(registry)
    assert account.record.id == "chat:101"
    assert [row.record.id for row in registry.list(role_id="r1")] == ["chat:101"]
    assert list(tmp_path.iterdir()) == []
    assert AccountRegistry({"r1"}.__contains__).list() == []


def test_index_refuses_cross_role_and_second_account_per_plugin():
    registry = AccountRegistry({"r1", "r2"}.__contains__)
    _register(registry)
    with pytest.raises(ValueError, match="已属于另一个角色"):
        _register(registry, role="r2")
    with pytest.raises(ValueError, match="该角色在这个渠道已有账号"):
        _register(registry, account="102", ref="two")
    with pytest.raises(ValueError, match="配置引用已属于"):
        _register(registry, account="103", ref="one", role="r2")
    with pytest.raises(ValueError, match="没有所属角色"):
        _register(registry, account="104", ref="four", role=None)
    with pytest.raises(ValueError, match="角色不存在"):
        _register(registry, account="105", ref="five", role="gone")
    # Another plugin is another channel: the same role may hold one there.
    other = registry.register(
        plugin_id="other",
        platform="chat",
        platform_account_id="101",
        config_ref="one",
        token="generation-1",
        role_id="r1",
    )
    assert other.record.id == "other:101"
    assert [row.record.id for row in registry.list()] == ["chat:101", "other:101"]


def test_unloaded_plugin_accounts_leave_the_index_and_stop_routing():
    registry = AccountRegistry({"r1"}.__contains__)
    account = _register(registry)
    registry.report(account.record.id, "generation-1", connection="online")
    access = registry.authorize(account.record.id, "r1")
    # The disposed plugin instance releases what it registered.
    registry.release(account.record.id, "generation-1")
    assert registry.list() == []
    assert not registry.validate_access(access)
    with pytest.raises(AccountNotFoundError):
        registry.authorize(account.record.id, "r1")


def test_candidate_generation_is_hidden_until_published():
    registry = AccountRegistry({"r1"}.__contains__)
    _register(registry, display_name="Running")
    # A disabled plugin does not register in the next generation at all.
    registry.publish_generation("next")
    assert registry.list() == []
    _register(registry, token="generation-2", generation="candidate")
    assert registry.list() == []
    registry.publish_generation("candidate")
    assert [row.record.id for row in registry.list()] == ["chat:101"]


def test_rules_are_saved_by_the_owning_plugin_before_the_index_changes():
    registry = AccountRegistry({"r1"}.__contains__)
    saved = AccountResponseRules(private_enabled=False)
    account = _register(registry, response_rules=saved)
    assert account.record.response_rules == saved
    with pytest.raises(RuntimeError, match="响应规则保存能力"):
        registry.set_response_rules(account.record.id, AccountResponseRules())

    written: list[tuple[str, AccountResponseRules]] = []
    registry.set_rules_handler("chat", lambda ref, rules: written.append((ref, rules)))
    updated = AccountResponseRules(group_enabled=False)
    registry.set_response_rules(account.record.id, updated)
    assert written == [("one", updated)]
    assert registry.get(account.record.id).record.response_rules == updated
    # A re-registration without rules keeps what the plugin saved.
    assert _register(registry).record.response_rules == updated


class _Deletion:
    """A plugin delete hook recording its steps, optionally failing one."""

    def __init__(self, fail: set[str] | None = None) -> None:
        self.steps: list[str] = []
        self._fail = fail or set()

    def _step(self, name: str) -> None:
        self.steps.append(name)
        if name in self._fail:
            self._fail.discard(name)
            raise OSError(f"{name} failed")

    def plan(self, config_ref: str) -> AccountDeletionPlan:
        async def disconnect() -> None:
            self._step("disconnect")

        async def purge() -> None:
            self._step("purge")

        self._step(f"plan:{config_ref}")
        return AccountDeletionPlan(disconnect, purge)


@pytest.mark.asyncio
async def test_failed_purge_keeps_the_account_and_a_retry_completes():
    registry = AccountRegistry({"r1"}.__contains__)
    account = _register(registry)
    deletion = _Deletion(fail={"purge"})
    registry.set_delete_handler("chat", deletion.plan)
    with pytest.raises(PermissionError, match="不属于"):
        await registry.delete(account.record.id, role_id="r2")

    with pytest.raises(OSError, match="purge failed"):
        await registry.delete(account.record.id, role_id="r1")
    assert [row.record.id for row in registry.list()] == ["chat:101"]
    await registry.delete(account.record.id, role_id="r1")
    assert deletion.steps == ["plan:one", "disconnect", "purge"] * 2
    assert registry.list() == []


@pytest.mark.asyncio
async def test_account_is_frozen_and_cannot_be_revived_while_deleting():
    registry = AccountRegistry({"r1"}.__contains__)
    account_id = _register(registry).record.id
    registry.report(account_id, "generation-1", connection="online")
    registry.set_rules_handler("chat", lambda *_: None)
    refused: list[str] = []

    def plan(_config_ref: str) -> AccountDeletionPlan:
        async def disconnect() -> None:
            for change in (
                lambda: registry.set_response_rules(
                    account_id, AccountResponseRules(group_enabled=False)
                ),
                # A newly prepared generation re-registering the identity.
                lambda: _register(registry, token="generation-2", generation="g2"),
            ):
                with pytest.raises(AccountDeletingError, match="正在删除") as error:
                    change()
                refused.append(str(error.value))
            # A retiring channel's final report is ignored, not applied.
            ignored = registry.report(
                account_id, "generation-1", connection="error", error="late"
            )
            assert ignored.connection == "online"

        async def purge() -> None:
            return None

        return AccountDeletionPlan(disconnect, purge)

    registry.set_delete_handler("chat", plan)
    await registry.delete(account_id, role_id="r1")
    assert refused == ["账号正在删除"] * 2
    assert registry.list() == []
    with pytest.raises(RuntimeError, match="no longer active"):
        registry.report(account_id, "generation-1", connection="online")
    # The same platform account added again gets the same ID back.
    assert _register(registry, token="generation-3").record.id == account_id


@pytest.mark.asyncio
async def test_role_deletion_deletes_every_loaded_account_of_the_role():
    registry = AccountRegistry({"r1", "r2"}.__contains__)
    _register(registry)
    registry.register(
        plugin_id="other",
        platform="other",
        platform_account_id="7",
        config_ref="seven",
        token="generation-1",
        role_id="r1",
    )
    _register(registry, account="102", ref="two", role="r2")
    chat, other = _Deletion(), _Deletion()
    registry.set_delete_handler("chat", chat.plan)
    registry.set_delete_handler("other", other.plan)

    assert await registry.delete_role_accounts("r1") == ["chat:101", "other:7"]
    assert chat.steps == ["plan:one", "disconnect", "purge"]
    assert other.steps == ["plan:seven", "disconnect", "purge"]
    assert [row.record.id for row in registry.list()] == ["chat:102"]


_PNG_AVATAR = "data:image/png;base64,iVBORw0KGgo="
_OVERSIZE_PNG = b"\x89PNG\r\n\x1a\n" + bytes(256 * 1024)


@pytest.mark.parametrize(
    ("avatar", "reason"),
    [
        ("https://cdn.example/bot.png", "data:image"),
        ("data:text/html;base64,PGh0bWw+", "data:image"),
        ("data:image/png;base64,PGh0bWw+", "PNG、JPEG"),
        ("data:image/jpeg;base64,iVBORw0KGgo=", "不符"),
        ("data:image/png;base64,iVBORw0KGgo", "base64"),
        ("data:image/png;base64," + base64.b64encode(_OVERSIZE_PNG).decode(), "KiB"),
    ],
    ids=[
        "remote-url",
        "non-image-mime",
        "non-image",
        "mime-mismatch",
        "bad-base64",
        "oversize",
    ],
)
def test_register_refuses_an_avatar_that_is_not_a_small_image_data_uri(avatar, reason):
    registry = AccountRegistry({"r1"}.__contains__)
    with pytest.raises(ValueError, match=reason):
        _register(registry, avatar_url=avatar)
    assert registry.list() == []


def test_empty_avatar_means_none_and_omitting_it_keeps_the_indexed_one():
    registry = AccountRegistry({"r1"}.__contains__)
    assert _register(registry, avatar_url=_PNG_AVATAR).record.avatar_url == (
        _PNG_AVATAR
    )
    assert _register(registry).record.avatar_url == _PNG_AVATAR
    assert _register(registry, avatar_url="").record.avatar_url == ""


def test_listeners_hear_only_real_published_account_changes():
    registry = AccountRegistry({"r1"}.__contains__)
    changed: list[str] = []
    registry.add_change_listener(changed.append)

    account = _register(registry, display_name="Bot")
    registry.report(account.record.id, "generation-1", connection="login_required")
    registry.report(account.record.id, "generation-1", connection="login_required")
    _register(registry, display_name="Bot")
    assert changed == ["chat:101", "chat:101"]

    registry.report(account.record.id, "generation-1", connection="online")
    _register(registry, avatar_url=_PNG_AVATAR)
    registry.report(
        account.record.id, "generation-1", connection="error", error="offline"
    )
    # A candidate generation is not visible until published.
    _register(registry, token="generation-2", generation="next")
    registry.release(account.record.id, "generation-1")
    assert changed == ["chat:101"] * 6

    registry.remove_change_listener(changed.append)
    _register(registry, token="generation-3")
    assert len(changed) == 6


@pytest.mark.asyncio
async def test_deleted_listeners_run_only_once_the_account_is_gone():
    registry = AccountRegistry({"r1"}.__contains__)
    account = _register(registry)
    registry.set_delete_handler("chat", _Deletion(fail={"purge"}).plan)
    deleted: list[str] = []
    registry.add_deleted_listener(deleted.append)

    with pytest.raises(OSError, match="purge failed"):
        await registry.delete(account.record.id, role_id="r1")
    assert deleted == []
    await registry.delete(account.record.id, role_id="r1")
    assert deleted == ["chat:101"]
