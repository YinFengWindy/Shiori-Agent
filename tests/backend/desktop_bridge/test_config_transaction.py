from __future__ import annotations

import json

import pytest

from desktop_bridge import config_transaction
from desktop_bridge.config_transaction import ConfigTransaction
from shiori_sdk.files.json import atomic_save_json


def test_commit_preserves_utf8_and_updates_both_files(tmp_path):
    path = tmp_path / "config.toml"
    transaction = ConfigTransaction(path, tmp_path)
    transaction.commit('[agent]\nname = "角色"\n', {"roles": [{"name": "角色"}]})
    assert '"角色"' in path.read_text(encoding="utf-8")
    assert (
        json.loads(transaction.roles_path.read_text(encoding="utf-8"))["roles"][0][
            "name"
        ]
        == "角色"
    )
    assert not transaction.journal_path.exists()


def test_role_file_failure_restores_configuration_and_roles(tmp_path, monkeypatch):
    transaction = ConfigTransaction(tmp_path / "config.toml", tmp_path)
    transaction.commit("old config", {"roles": []})
    original = config_transaction.atomic_save_text
    failed = False

    def fail_roles_once(path, content):
        nonlocal failed
        if path == transaction.roles_path and not failed:
            failed = True
            raise OSError("disk write failed")
        original(path, content)

    monkeypatch.setattr(config_transaction, "atomic_save_text", fail_roles_once)
    with pytest.raises(OSError, match="disk write failed"):
        transaction.commit("new config", {"roles": [{"id": "new"}]})
    assert transaction.config_path.read_text(encoding="utf-8") == "old config"
    assert json.loads(transaction.roles_path.read_text(encoding="utf-8")) == {
        "roles": []
    }


def test_recovery_rolls_back_interrupted_commit(tmp_path):
    transaction = ConfigTransaction(tmp_path / "config.toml", tmp_path)
    transaction.commit("new config", {"roles": []})
    atomic_save_json(
        transaction.journal_path,
        {
            "state": "prepared",
            "config_before": "old config",
            "roles_before": None,
        },
    )
    transaction.recover()
    assert transaction.config_path.read_text(encoding="utf-8") == "old config"
    assert not transaction.roles_path.exists()


def test_recovery_keeps_completed_commit(tmp_path):
    transaction = ConfigTransaction(tmp_path / "config.toml", tmp_path)
    transaction.commit("new config")
    atomic_save_json(
        transaction.journal_path,
        {
            "state": "committed",
            "config_before": "old config",
            "roles_before": None,
        },
    )
    transaction.recover()
    assert transaction.config_path.read_text(encoding="utf-8") == "new config"
