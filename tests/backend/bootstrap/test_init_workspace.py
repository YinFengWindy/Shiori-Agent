import json
import importlib
import shutil
import sys
from pathlib import Path

import pytest
import tomllib

from bootstrap import init_workspace as workspace_init
from bootstrap.paths import REPOSITORY_ROOT


def test_init_upgrades_plugin_json_from_explicit_workspace(tmp_path, monkeypatch):
    workspace = tmp_path / "workspace"
    package = tmp_path / "packages/demo"
    package.mkdir(parents=True)
    (package / "manifest.yaml").write_text(
        "api: 2\nid: demo\ncapabilities: []\n", encoding="utf-8"
    )
    legacy = workspace / "plugins/demo/plugin_config.json"
    legacy.parent.mkdir(parents=True)
    legacy.write_text('{"value":"kept"}', encoding="utf-8")
    path = tmp_path / "config.toml"
    path.write_text("", encoding="utf-8")
    monkeypatch.setattr(
        "agent.plugin_config_migration.plugin_roots", lambda: [package.parent]
    )
    monkeypatch.setattr("agent.plugin_config_migration.REPOSITORY_ROOT", tmp_path)
    workspace_init.init_workspace(config_path=path, workspace=workspace)
    assert tomllib.loads(path.read_text(encoding="utf-8"))["plugins"]["demo"] == {
        "value": "kept"
    }
    assert not legacy.exists()


def test_init_workspace_creates_expected_assets(tmp_path):
    config_path = tmp_path / "config.toml"
    workspace = tmp_path / "workspace"

    summary = workspace_init.init_workspace(
        config_path=config_path,
        workspace=workspace,
    )

    assert config_path.exists()
    config_text = config_path.read_text(encoding="utf-8")
    registrations = tomllib.loads(config_text)["llm"]["registrations"]
    assert registrations == []
    assert "[llm.vl]" not in config_text
    assert (workspace / "sessions.db").exists()
    assert not (workspace / "observe").exists()
    assert not (workspace / "memes").exists()
    assert (workspace / "memory" / "consolidation_writes.db").exists()
    assert (workspace / "memory" / "journal").is_dir()
    assert (workspace / "plugin-data" / "default_memory" / "memory2.db").exists()
    assert json.loads((workspace / "mcp_servers.json").read_text(encoding="utf-8")) == {
        "servers": {}
    }
    assert json.loads(
        (workspace / "proactive_sources.json").read_text(encoding="utf-8")
    ) == {"sources": []}
    assert (workspace / "skills").is_dir()
    assert not (workspace / "drift" / "skills").exists()
    assert (workspace / "roles" / "roles.json").exists()
    assert json.loads(
        (workspace / "roles" / "roles.json").read_text(encoding="utf-8")
    ) == {"version": 2, "roles": []}
    assert (workspace / "roles" / "assets").is_dir()
    assert any(path == config_path for path in summary.created)


def test_init_workspace_respects_force_for_text_assets(tmp_path):
    config_path = tmp_path / "config.toml"
    workspace = tmp_path / "workspace"

    workspace_init.init_workspace(
        config_path=config_path,
        workspace=workspace,
    )
    config_text = config_path.read_text(encoding="utf-8").replace(
        "max_iterations = 40",
        "max_iterations = 99",
        1,
    )
    config_path.write_text(config_text, encoding="utf-8")

    summary_skip = workspace_init.init_workspace(
        config_path=config_path,
        workspace=workspace,
    )
    assert "max_iterations = 99" in config_path.read_text(encoding="utf-8")
    assert any(path == config_path for path in summary_skip.skipped)

    summary_force = workspace_init.init_workspace(
        config_path=config_path,
        workspace=workspace,
        force=True,
    )
    assert "[llm]" in config_path.read_text(encoding="utf-8")
    assert any(path == config_path for path in summary_force.overwritten)


def test_frozen_workspace_copies_the_bundled_template(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    template = tmp_path / "bundle/config/examples/config.example.toml"
    template.parent.mkdir(parents=True)
    original = workspace_init.CONFIG_TEMPLATE_PATH.read_text(encoding="utf-8")
    template.write_text(original + "\n# bundled template\n", encoding="utf-8")
    # A frozen workspace must initialize memory from its own bundled package.
    _ = shutil.copytree(
        REPOSITORY_ROOT / "plugins/default_memory/backend",
        tmp_path / "bundle/plugins/default_memory/backend",
        ignore=shutil.ignore_patterns("__pycache__"),
    )
    with monkeypatch.context() as scoped:
        scoped.setattr(sys, "_MEIPASS", str(tmp_path / "bundle"), raising=False)
        importlib.reload(workspace_init)
        try:
            target = tmp_path / "user/config.toml"
            workspace_init.init_workspace(
                config_path=target, workspace=tmp_path / "user"
            )
            assert target.read_bytes() == template.read_bytes()
        finally:
            scoped.undo()
            importlib.reload(workspace_init)


def test_config_example_does_not_expose_default_memory_private_config() -> None:
    text = workspace_init.CONFIG_TEMPLATE_PATH.read_text(encoding="utf-8")

    assert "[memory.embedding]" in text
    assert "[memory.retrieval]" not in text
    assert "[memory.gate]" not in text
    assert "[memory.hyde]" not in text
    assert "output_dimensionality" not in text
    assert "[memory_v2]" not in text


def test_mcp_servers_example_is_public_empty_configuration() -> None:
    example_path = REPOSITORY_ROOT / "config/examples/mcp_servers.example.json"
    payload = json.loads(example_path.read_text(encoding="utf-8"))

    assert payload == {"servers": {}}
