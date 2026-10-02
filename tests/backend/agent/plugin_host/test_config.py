"""Plugin config grants independent snapshots and explicit missing attributes."""

import pytest
from agent.plugin_host.config import PluginConfig


def test_config_copies_values_and_returns_independent_top_level_snapshot():
    values = {"token": "old"}
    config = PluginConfig(values)
    values["token"] = "new"
    assert config.token == "old"
    snapshot = config.as_dict()
    snapshot["token"] = "modified"
    assert config.get("token") == "old"
    assert config.get("missing", 3) == 3
    with pytest.raises(AttributeError):
        _ = config.missing


def test_config_exposes_raw_reference_without_changing_resolved_values():
    config = PluginConfig(
        {"client_secret": "expanded-secret"},
        raw_values={"client_secret": "${QQBOT_SECRET}"},
    )
    assert config.get("client_secret") == "expanded-secret"
    raw = config.raw_as_dict()
    assert raw["client_secret"] == "${QQBOT_SECRET}"
    raw["client_secret"] = "changed"
    assert config.raw_as_dict()["client_secret"] == "${QQBOT_SECRET}"


def test_stored_secret_resolution_uses_environment_then_workspace_file(
    tmp_path, monkeypatch
):
    from agent import config as agent_config

    config = PluginConfig({})
    monkeypatch.setenv("CHANNEL_SECRET", "environment-secret")
    assert config.resolve_reference("${CHANNEL_SECRET}") == "environment-secret"
    monkeypatch.delenv("CHANNEL_SECRET")
    memory = tmp_path / "memory"
    memory.mkdir()
    (memory / "CHANNEL_SECRET").write_text("file-secret", encoding="utf-8")
    monkeypatch.setattr(agent_config, "resolve_default_workspace", lambda: tmp_path)
    assert config.resolve_reference("${CHANNEL_SECRET}") == "file-secret"
