from __future__ import annotations

from pathlib import Path

from shiori_sdk.testing.memory import FakeMemoryStorage

from plugins.default_memory.backend.config import (
    ensure_default_memory_config_file,
    load_default_memory_config,
    resolve_memory_db_path,
)


def test_clean_workspace_creates_editable_defaults_in_data_directory(
    tmp_path: Path,
) -> None:
    workspace = tmp_path / "workspace"
    path = ensure_default_memory_config_file(
        workspace=workspace, storage=FakeMemoryStorage()
    )

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

    assert resolve_memory_db_path(
        workspace=tmp_path, default_config=cfg, storage=FakeMemoryStorage()
    ) == (tmp_path / "plugin-data" / "default_memory" / "memory2.db")
