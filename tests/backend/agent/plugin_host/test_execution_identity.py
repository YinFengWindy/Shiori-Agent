"""Desktop-session execution identity survives backend reconnects without granting trust."""

import pytest

from shiori_sdk.kernel import PackageContractError
from agent.plugin_host.execution_identity import PluginExecutionIdentity


def test_execution_identity_rejects_changed_bytes_paths_and_reused_directories(
    tmp_path, monkeypatch
):
    monkeypatch.setenv("SHIORI_DESKTOP_APPLICATION_SESSION_ID", "first-session")
    directory = tmp_path / "plugins" / "one"
    identity = PluginExecutionIdentity(tmp_path)
    assert identity.matches("one", directory, "a" * 64)
    identity.record("one", directory, "a" * 64)
    reconnected = PluginExecutionIdentity(tmp_path)
    assert reconnected.matches("one", directory, "a" * 64)
    assert not reconnected.matches("one", directory, "b" * 64)
    assert not reconnected.matches("one", directory.with_name("moved"), "a" * 64)
    assert not reconnected.matches("replacement-id", directory, "b" * 64)
    with pytest.raises(PackageContractError, match="重启"):
        reconnected.record("one", directory, "b" * 64)
    monkeypatch.setenv("SHIORI_DESKTOP_APPLICATION_SESSION_ID", "next-session")
    assert reconnected.matches("one", directory, "b" * 64)
    reconnected.record("one", directory, "b" * 64)
    assert not (tmp_path / "private_runtime/plugin-trust.json").exists()


def test_invalid_current_execution_record_is_not_silently_replaced(
    tmp_path, monkeypatch
):
    monkeypatch.setenv("SHIORI_DESKTOP_APPLICATION_SESSION_ID", "session")
    identity = PluginExecutionIdentity(tmp_path)
    identity.path.parent.mkdir()
    identity.path.write_text(
        '{"version":1,"session":"session","packages":[]}', encoding="utf-8"
    )
    with pytest.raises(ValueError, match="执行记录"):
        identity.record("one", tmp_path / "one", "a" * 64)
