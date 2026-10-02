"""Host memory storage migrates default_memory overrides through the plugin's loader."""

from __future__ import annotations

from pathlib import Path

import pytest
from bootstrap.memory_capabilities import HostMemoryStorage

from plugins.default_memory.backend.config import (
    ensure_default_memory_config_file,
    load_default_memory_config,
)


@pytest.mark.parametrize("location", ["workspace", "package", "old", "old-backend"])
def test_every_legacy_layout_migrates_once_and_survives_package_replacement(
    tmp_path, monkeypatch, location
):
    monkeypatch.setattr("agent.plugin_host.local_config.REPOSITORY_ROOT", tmp_path)
    workspace = tmp_path / "workspace"
    package = tmp_path / "plugins/default_memory/backend"
    source = {
        "workspace": workspace / "plugins/default_memory/config.local.toml",
        "package": package / "config.local.toml",
        "old": tmp_path / "apps/backend/plugins/default_memory/config.local.toml",
        "old-backend": tmp_path
        / "apps/backend/plugins/default_memory/backend/config.local.toml",
    }[location]
    source.parent.mkdir(parents=True)
    source.write_text(
        'db_path = "user.db"\n[retrieval]\ntop_k_history = 21\n', encoding="utf-8"
    )
    storage = HostMemoryStorage()

    cfg = load_default_memory_config(
        plugin_dir=package, workspace=workspace, storage=storage
    )

    assert cfg.db_path == "user.db"
    assert cfg.retrieval.top_k_history == 21
    target = ensure_default_memory_config_file(
        plugin_dir=package, workspace=workspace, storage=storage
    )
    assert target == workspace / "plugin-data/default_memory/config.local.toml"
    assert not source.exists()
    package.mkdir(parents=True, exist_ok=True)
    (package / "config.local.toml").write_text(
        'db_path = "replacement.db"\n', encoding="utf-8"
    )
    assert (
        load_default_memory_config(
            plugin_dir=package, workspace=workspace, storage=storage
        )
        == cfg
    )


def test_workspace_config_is_preserved_when_legacy_also_exists(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    target = workspace / "plugin-data" / "default_memory" / "config.local.toml"
    target.parent.mkdir(parents=True)
    target.write_text('db_path = "current.db"\n', encoding="utf-8")
    legacy = workspace / "plugins" / "default_memory" / "config.local.toml"
    legacy.parent.mkdir(parents=True)
    legacy.write_text('db_path = "old.db"\n', encoding="utf-8")

    cfg = load_default_memory_config(workspace=workspace, storage=HostMemoryStorage())

    assert cfg.db_path == "current.db"
    assert legacy.exists()
