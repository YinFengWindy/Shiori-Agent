"""Credentials live only in the pet's private files, one file per role."""

import os

import pytest

from plugins.desktop_pet.backend.bilibili_credentials import (
    BilibiliCredentials,
    BilibiliCredentialStore,
)

CREDENTIALS = BilibiliCredentials(
    uid=42, uname="主播", cookies={"SESSDATA": "s"}, refresh_token="r"
)


def test_credentials_round_trip_under_plugin_data_and_delete(tmp_path):
    store = BilibiliCredentialStore(tmp_path)
    assert store.read("role") is None
    store.write("role", CREDENTIALS)
    assert BilibiliCredentialStore(tmp_path).read("role") == CREDENTIALS
    assert store.root == tmp_path / "plugin-data/desktop_pet/bilibili-logins"
    store.delete("role")
    assert store.read("role") is None
    assert list(store.root.iterdir()) == []


def test_prune_keeps_only_existing_roles_and_ids_cannot_escape(tmp_path):
    store = BilibiliCredentialStore(tmp_path)
    store.write("kept", CREDENTIALS)
    store.write("gone", CREDENTIALS)
    store.prune({"kept"})
    assert [path.name for path in store.root.iterdir()] == ["kept.json"]
    with pytest.raises(ValueError, match="不安全"):
        store.write("../escape", CREDENTIALS)


@pytest.mark.skipif(os.name != "posix", reason="POSIX 权限位；Windows 沿用目录 ACL")
def test_credentials_are_owner_only_on_posix(tmp_path):
    store = BilibiliCredentialStore(tmp_path)
    store.write("role", CREDENTIALS)
    assert store.root.stat().st_mode & 0o777 == 0o700
    assert (store.root / "role.json").stat().st_mode & 0o777 == 0o600
