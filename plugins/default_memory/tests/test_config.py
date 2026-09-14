from __future__ import annotations

from pathlib import Path

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


def test_clean_workspace_uses_packaged_default_without_creating_data(
    tmp_path: Path,
) -> None:
    workspace = tmp_path / "workspace"
    path = ensure_default_memory_config_file(workspace=workspace)

    assert path.name == "config.local.toml"
    assert "plugin-data" not in path.parts
    assert not (workspace / "plugin-data").exists()


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
