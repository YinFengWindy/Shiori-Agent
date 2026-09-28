from __future__ import annotations

import pytest

from plugins.qq.backend.accounts_store import (
    QQAccountsStore,
    QQConnectionConfig,
    QQPendingConnection,
)


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


def test_private_store_rejects_unknown_connection_mode(tmp_path):
    store = QQAccountsStore(tmp_path)
    store.path.parent.mkdir(parents=True)
    store.path.write_text(
        '{"version":1,"accounts":[{"ref":"a","ws_uri":"ws://a",'
        '"ws_token":"","mode":"unknown"}]}',
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="连接模式"):
        store.load()


def test_pending_credentials_round_trip_without_replacing_active_connection(tmp_path):
    store = QQAccountsStore(tmp_path)
    config = QQConnectionConfig(
        "account",
        "ws://active:3001",
        "working",
        expected_uin="101",
        verified=True,
        pending=QQPendingConnection("ws://pending:3002", "new", 7),
    )
    store.save({config.ref: config})
    assert store.load()[config.ref] == config
    public = store.load()[config.ref].public_dict()
    assert public["ws_uri"] == "ws://pending:3002"
    assert "working" not in str(public) and "new" not in str(public)
