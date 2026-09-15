"""Host trust persistence is exact, atomic and fails closed on invalid records."""

import pytest

from agent.plugin_host.trust_store import PluginTrustStore


def test_approvals_are_bound_to_path_and_content_and_survive_reopen(
    tmp_path, monkeypatch
):
    store = PluginTrustStore(tmp_path)
    package = tmp_path / "plugins" / "demo"
    store.approve(package, "a" * 64)
    assert PluginTrustStore(tmp_path).is_trusted(package, "a" * 64)
    assert not store.is_trusted(package, "b" * 64)
    assert not store.is_trusted(package.with_name("other"), "a" * 64)
    before = store.path.read_bytes()

    def fail(*_args):
        raise OSError("disk failure")

    monkeypatch.setattr("agent.plugin_host.trust_store.atomic_save_text", fail)
    with pytest.raises(OSError, match="disk failure"):
        store.approve(package, "b" * 64)
    assert store.path.read_bytes() == before
    assert store.path.parent == tmp_path / "private_runtime"


def test_invalid_trust_file_does_not_grant_or_silently_reset(tmp_path):
    store = PluginTrustStore(tmp_path)
    store.path.parent.mkdir()
    store.path.write_text(
        '{"version": 1, "approvals": {"demo": true}}', encoding="utf-8"
    )
    with pytest.raises(ValueError):
        store.is_trusted(tmp_path / "demo", "a" * 64)


def test_same_desktop_session_cannot_activate_new_approval_after_bridge_restart(
    tmp_path, monkeypatch
):
    monkeypatch.setenv("SHIORI_DESKTOP_APPLICATION_SESSION_ID", "first-app")
    store = PluginTrustStore(tmp_path)
    package = tmp_path / "plugins" / "demo"
    store.approve(package, "a" * 64)
    assert store.is_trusted(package, "a" * 64)
    assert not PluginTrustStore(tmp_path).is_trusted(package, "a" * 64, activation=True)
    monkeypatch.setenv("SHIORI_DESKTOP_APPLICATION_SESSION_ID", "next-app")
    assert PluginTrustStore(tmp_path).is_trusted(package, "a" * 64, activation=True)
