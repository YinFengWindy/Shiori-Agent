from __future__ import annotations

import json

import pytest

from plugins.qq.backend.accounts_store import QQAccountsStore, QQConnectionConfig


def test_private_store_rejects_duplicate_managed_references(tmp_path):
    store = QQAccountsStore(tmp_path)
    store.path.parent.mkdir(parents=True)
    store.path.write_text(
        json.dumps(
            {
                "version": 1,
                "accounts": [
                    {
                        "ref": "same",
                        "mode": "managed",
                        "ws_uri": "ws://127.0.0.1:1",
                        "ws_token": "a",
                    },
                    {
                        "ref": "same",
                        "mode": "managed",
                        "ws_uri": "ws://127.0.0.1:2",
                        "ws_token": "b",
                    },
                ],
            }
        ),
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="重复"):
        store.load()


def test_managed_credentials_round_trip_without_leaking_into_public_settings(tmp_path):
    store = QQAccountsStore(tmp_path)
    config = QQConnectionConfig(
        "account",
        "ws://127.0.0.1:3001",
        "private-token",
        expected_uin="101",
        verified=True,
        role_id="mira",
    )
    store.save({config.ref: config})

    assert store.load()[config.ref] == config
    assert store.load()[config.ref].public_dict() == {
        "ref": "account",
        "expected_uin": "101",
        "display_name": "",
        "auto_connect": True,
        "verified": True,
        "mode": "managed",
        "role_id": "mira",
    }
    assert "private-token" not in str(config.public_dict())
