from __future__ import annotations

from pathlib import Path

import pytest

from plugins.default_memory.backend.config import (
    ensure_default_memory_config_file,
    load_default_memory_config,
    resolve_memory_db_path,
)


def test_workspace_legacy_config_migrates_and_wins(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    legacy = workspace / "plugins" / "default_memory" / "config.local.toml"
    legacy.parent.mkdir(parents=True)
    legacy.write_text('db_path = "legacy.db"\n', encoding="utf-8")

    cfg = load_default_memory_config(workspace=workspace)

    target = workspace / "plugin-data" / "default_memory" / "config.local.toml"
    assert cfg.db_path == "legacy.db"
    assert target.exists()
    assert not legacy.exists()


def test_workspace_config_is_preserved_when_legacy_also_exists(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    target = workspace / "plugin-data" / "default_memory" / "config.local.toml"
    target.parent.mkdir(parents=True)
    target.write_text('db_path = "current.db"\n', encoding="utf-8")
    legacy = workspace / "plugins" / "default_memory" / "config.local.toml"
    legacy.parent.mkdir(parents=True)
    legacy.write_text('db_path = "old.db"\n', encoding="utf-8")

    cfg = load_default_memory_config(workspace=workspace)

    assert cfg.db_path == "current.db"
    assert legacy.exists()


def test_clean_workspace_creates_editable_defaults_in_data_directory(
    tmp_path: Path,
) -> None:
    workspace = tmp_path / "workspace"
    path = ensure_default_memory_config_file(workspace=workspace)

    assert path.name == "config.local.toml"
    assert path == workspace / "plugin-data" / "default_memory" / "config.local.toml"
    assert path.is_file()


def test_default_memory_config_reads_example_defaults() -> None:
    cfg = load_default_memory_config()

    assert cfg.retrieval.top_k_history == 8
    assert cfg.retrieval.thresholds.procedure == 0.66
    assert cfg.retrieval.inject.max_chars == 6000


def test_default_memory_config_local_overrides(tmp_path: Path) -> None:
    (tmp_path / "config.local.toml").write_text(
        """
db_path = "custom/memory.db"

[retrieval]
score_threshold = 0.7

[retrieval.thresholds]
event = 0.8

[retrieval.inject]
max_chars = 3000
""",
        encoding="utf-8",
    )

    cfg = load_default_memory_config(plugin_dir=tmp_path)

    assert cfg.db_path == "custom/memory.db"
    assert cfg.retrieval.top_k_history == 8
    assert cfg.retrieval.score_threshold == 0.7
    assert cfg.retrieval.thresholds.event == 0.8
    assert cfg.retrieval.inject.max_chars == 3000


def test_default_memory_db_path_resolves_under_workspace(tmp_path: Path) -> None:
    cfg = load_default_memory_config(plugin_dir=tmp_path)

    assert resolve_memory_db_path(workspace=tmp_path, default_config=cfg) == (
        tmp_path / "memory" / "memory2.db"
    )


@pytest.mark.parametrize("location", ["package", "old", "old-backend"])
def test_all_package_layouts_preserve_user_overrides_after_replacement(
    tmp_path, monkeypatch, location
):
    monkeypatch.setattr("agent.plugin_host.local_config.REPOSITORY_ROOT", tmp_path)
    workspace = tmp_path / "workspace"
    package = tmp_path / "plugins/default_memory/backend"
    source = {
        "package": package / "config.local.toml",
        "old": tmp_path / "apps/backend/plugins/default_memory/config.local.toml",
        "old-backend": tmp_path
        / "apps/backend/plugins/default_memory/backend/config.local.toml",
    }[location]
    source.parent.mkdir(parents=True)
    source.write_text(
        'db_path = "user.db"\n[retrieval]\ntop_k_history = 21\n', encoding="utf-8"
    )
    cfg = load_default_memory_config(plugin_dir=package, workspace=workspace)
    assert cfg.db_path == "user.db"
    assert cfg.retrieval.top_k_history == 21
    target = ensure_default_memory_config_file(plugin_dir=package, workspace=workspace)
    assert target == workspace / "plugin-data/default_memory/config.local.toml"
    assert not source.exists()
    package.mkdir(parents=True, exist_ok=True)
    (package / "config.local.toml").write_text(
        'db_path = "replacement.db"\n', encoding="utf-8"
    )
    assert load_default_memory_config(plugin_dir=package, workspace=workspace) == cfg
