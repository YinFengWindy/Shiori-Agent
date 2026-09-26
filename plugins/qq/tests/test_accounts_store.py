from __future__ import annotations

from plugins.qq.backend.accounts_store import QQAccountsStore, QQConnectionConfig


def test_legacy_connection_migrates_once_without_overwriting_private_edits(tmp_path):
    store = QQAccountsStore(tmp_path)
    first = store.migrate_legacy(
        bot_uin="101",
        ws_uri="ws://localhost:3001",
        ws_token="first",
        timeout_seconds=7,
    )
    assert first["legacy"].expected_uin == "101"
    assert first["legacy"].ws_token == "first"
    assert store.path.is_relative_to(tmp_path / "plugin-data" / "qq")

    second = store.migrate_legacy(
        bot_uin="202",
        ws_uri="ws://other:3002",
        ws_token="second",
        timeout_seconds=3,
    )
    assert second == first
    assert "first" not in str(first["legacy"].public_dict())


def test_private_store_rejects_duplicate_references(tmp_path):
    store = QQAccountsStore(tmp_path)
    store.path.parent.mkdir(parents=True)
    store.path.write_text(
        '{"version":1,"accounts":[{"ref":"same","ws_uri":"ws://a","ws_token":""},'
        '{"ref":"same","ws_uri":"ws://b","ws_token":""}]}',
        encoding="utf-8",
    )
    try:
        store.load()
    except ValueError as error:
        assert "重复" in str(error)
    else:
        raise AssertionError("duplicate references must fail")


def test_migration_does_not_duplicate_an_existing_qq_identity(tmp_path):
    store = QQAccountsStore(tmp_path)
    existing = QQConnectionConfig(
        "already", "ws://localhost:3001", "secret", expected_uin="101", verified=True
    )
    store.save({"already": existing})
    migrated = store.migrate_legacy(
        bot_uin="101",
        ws_uri="ws://localhost:3001",
        ws_token="secret",
        timeout_seconds=5,
    )
    assert migrated == {"already": existing}
