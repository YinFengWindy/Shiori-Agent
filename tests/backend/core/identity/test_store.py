from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import pytest

from shiori_sdk.accounts.models import AccountRecord
from core.identity import IdentityChat, UserIdentity, UserIdentityStore
from shiori_sdk.channels.identity import IdentityScope


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
        {
            "account_id": "qq:101",
            "channel": "qq",
            "chat_id": "902",
            "context_since": identity.bound_at,
        }
    ]

    store.unbind(identity.id)
    assert other.match(QQ_A, "902") is None
    assert len(changes) == 2
    with pytest.raises(KeyError):
        store.unbind(identity.id)


def test_pairing_again_keeps_the_binding_and_records_the_new_chat(
    tmp_path: Path,
) -> None:
    ticks = iter(
        datetime(2026, 9, 29, 10, minute, tzinfo=timezone.utc) for minute in range(10)
    )
    now = next(ticks)
    store = UserIdentityStore(tmp_path, clock=lambda: now)
    first = _pair(store, QQ_A, "902", "platform", ("qq", "902"))
    now = next(ticks)
    second = _pair(store, QQ_B, "902", "platform", ("qq", "902"))
    assert first is not None and second is not None

    assert second.id == first.id
    # A fresh bound_at tells the desktop the code it shows was used.
    assert second.bound_at > first.bound_at
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


def test_chat_context_boundary_survives_repair_and_moves_only_on_new_binding(tmp_path):
    now = datetime(2026, 1, 1, tzinfo=timezone.utc)
    store = UserIdentityStore(tmp_path, clock=lambda: now)
    first = _pair(store, QQ_A, "902", "platform", ("qq", "902"))
    assert first is not None
    assert first.chats[0].context_since == now.isoformat()
    now = datetime(2026, 1, 2, tzinfo=timezone.utc)
    paired_again = _pair(store, QQ_A, "902", "platform", ("qq", "902"))
    assert paired_again is not None
    assert paired_again.chats == first.chats
    store.remember_chat(first.id, IdentityChat(QQ_A.id, "qq", "902"))
    received = datetime(2026, 1, 1, 23, 59, tzinfo=timezone.utc)
    store.remember_chat(
        first.id, IdentityChat(QQ_B.id, "qq_b", "902"), context_since=received
    )
    [reloaded] = UserIdentityStore(tmp_path).list()
    assert reloaded.chats[0].context_since == first.chats[0].context_since
    assert reloaded.chats[1].context_since == received.isoformat()
    store.unbind(first.id)
    rebound = _pair(store, QQ_A, "902", "platform", ("qq", "902"))
    assert rebound is not None and rebound.id != first.id
    assert rebound.chats[0].context_since == now.isoformat()


def test_legacy_chat_keeps_unbounded_history_when_repaired(tmp_path):
    store = UserIdentityStore(tmp_path)
    identity = _pair(store, QQ_A, "902", "platform", ("qq", "902"))
    assert identity is not None
    path = tmp_path / "user_identities.json"
    payload = json.loads(path.read_text(encoding="utf-8"))
    payload["identities"][0]["chats"][0].pop("context_since")
    path.write_text(json.dumps(payload), encoding="utf-8")
    assert UserIdentityStore(tmp_path).list()[0].chats[0].context_since == ""
    repaired = _pair(store, QQ_A, "902", "platform", ("qq", "902"))
    assert repaired is not None and repaired.chats[0].context_since == ""


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


def test_malformed_file_fails_without_using_up_the_code(tmp_path: Path) -> None:
    store = UserIdentityStore(tmp_path)
    code = store.create_pairing_code().code
    path = tmp_path / "user_identities.json"
    path.write_text('{"version": 99}', encoding="utf-8")
    chat = IdentityChat(QQ_A.id, "qq", "902")

    with pytest.raises(ValueError, match="格式无效"):
        store.pair(code, record=QQ_A, user_id="902", scope="platform", chat=chat)
    path.unlink()
    assert store.pair(code, record=QQ_A, user_id="902", scope="platform", chat=chat)
