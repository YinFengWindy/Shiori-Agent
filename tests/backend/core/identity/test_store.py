from __future__ import annotations

import json
from pathlib import Path

import pytest

from core.accounts import AccountRecord
from core.identity import IdentityChat, IdentityScope, UserIdentity, UserIdentityStore


def _account(plugin_id: str, platform_account_id: str) -> AccountRecord:
    return AccountRecord(
        id=f"{plugin_id}:{platform_account_id}",
        plugin_id=plugin_id,
        platform=plugin_id,
        platform_account_id=platform_account_id,
        config_ref=platform_account_id,
        role_id="mira",
    )


QQ_A = _account("qq", "101")
QQ_B = _account("qq", "102")
BOT_A = _account("qqbot", "app-a")
BOT_B = _account("qqbot", "app-b")


def _pair(
    store: UserIdentityStore,
    record: AccountRecord,
    user: str,
    scope: IdentityScope,
    chat: tuple[str, str],
) -> UserIdentity | None:
    return store.pair(
        store.create_pairing_code().code,
        record=record,
        user_id=user,
        scope=scope,
        chat=IdentityChat(record.id, *chat),
    )


def test_platform_scope_applies_to_every_account_of_the_plugin(
    tmp_path: Path,
) -> None:
    store = UserIdentityStore(tmp_path)
    identity = _pair(store, QQ_A, "902", "platform", ("qq", "902"))

    assert identity is not None
    assert store.match(QQ_B, "902") == identity
    assert store.match(QQ_B, "903") is None
    assert store.match(_account("telegram", "101"), "902") is None


def test_account_scope_applies_only_to_the_pairing_account(tmp_path: Path) -> None:
    store = UserIdentityStore(tmp_path)
    identity = _pair(store, BOT_A, "open-1", "account", ("qqbot", "c2c:open-1"))

    assert store.match(BOT_A, "open-1") == identity
    assert store.match(BOT_B, "open-1") is None


def test_only_the_pending_code_binds(tmp_path: Path) -> None:
    store = UserIdentityStore(tmp_path)
    code = store.create_pairing_code().code
    chat = IdentityChat(QQ_A.id, "qq", "902")

    def pair(text: str) -> UserIdentity | None:
        return store.pair(text, record=QQ_A, user_id="902", scope="platform", chat=chat)

    assert pair("hello") is None
    assert store.list() == []
    assert pair(code) is not None
    assert pair(code) is None
    assert len(store.list()) == 1


def test_bindings_persist_and_unbind_removes_them(tmp_path: Path) -> None:
    changes: list[None] = []
    store = UserIdentityStore(tmp_path)
    store.add_change_listener(lambda: changes.append(None))
    identity = _pair(store, QQ_A, "902", "platform", ("qq", "902"))
    assert identity is not None

    # Another instance over the same workspace reads the same bindings.
    other = UserIdentityStore(tmp_path)
    assert other.list() == [identity]
    saved = json.loads((tmp_path / "user_identities.json").read_text("utf-8"))
    assert saved["identities"][0]["chats"] == [
        {"account_id": "qq:101", "channel": "qq", "chat_id": "902"}
    ]

    store.unbind(identity.id)
    assert other.match(QQ_A, "902") is None
    assert len(changes) == 2
    with pytest.raises(KeyError):
        store.unbind(identity.id)


def test_pairing_again_keeps_the_binding_and_records_the_new_chat(
    tmp_path: Path,
) -> None:
    store = UserIdentityStore(tmp_path)
    first = _pair(store, QQ_A, "902", "platform", ("qq", "902"))
    second = _pair(store, QQ_B, "902", "platform", ("qq", "902"))
    assert first is not None and second is not None

    assert second.id == first.id
    assert second.bound_at == first.bound_at
    assert {chat.account_id for chat in second.chats} == {QQ_A.id, QQ_B.id}
    assert store.list() == [second]


def test_remembering_a_known_chat_changes_nothing(tmp_path: Path) -> None:
    changes: list[None] = []
    store = UserIdentityStore(tmp_path)
    identity = _pair(store, QQ_A, "902", "platform", ("qq", "902"))
    assert identity is not None
    store.add_change_listener(lambda: changes.append(None))

    store.remember_chat(identity.id, IdentityChat(QQ_A.id, "qq", "902"))
    assert changes == []
    store.remember_chat(identity.id, IdentityChat(QQ_B.id, "qq", "902"))
    assert len(changes) == 1
    assert len(store.list()[0].chats) == 2


def test_forgetting_an_account_drops_its_bindings_and_chats(tmp_path: Path) -> None:
    changes: list[None] = []
    store = UserIdentityStore(tmp_path)
    user = _pair(store, QQ_A, "902", "platform", ("qq", "902"))
    _pair(store, QQ_B, "902", "platform", ("qq", "902"))
    bot = _pair(store, BOT_A, "open-1", "account", ("qqbot", "c2c:open-1"))
    assert user is not None and bot is not None
    store.add_change_listener(lambda: changes.append(None))

    store.forget_account(QQ_A.id)
    store.forget_account(BOT_A.id)
    store.forget_account(BOT_B.id)

    [kept] = store.list()
    assert kept.id == user.id
    assert [chat.account_id for chat in kept.chats] == [QQ_B.id]
    assert store.match(BOT_A, "open-1") is None
    # An account without bindings or chats changes nothing.
    assert len(changes) == 2
