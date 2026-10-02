from __future__ import annotations

from pathlib import Path

from shiori_sdk.testing.memory import FakeMemoryStorage

from plugins.default_memory.backend import config as config_module
from plugins.default_memory.backend.config import (
    ensure_default_memory_config_file,
    load_default_memory_config,
    render_default_memory_config,
    resolve_memory_db_path,
)


class _RecordingStorage(FakeMemoryStorage):
    """Records what the plugin asks the host storage port to resolve."""

    def __init__(self) -> None:
        self.calls: list[dict[str, object]] = []

    def resolve_config(self, **kwargs) -> Path:
        self.calls.append(kwargs)
        return super().resolve_config(**kwargs)


def test_loader_and_ensure_resolve_through_storage_with_plugin_identity(
    tmp_path: Path,
) -> None:
    workspace = tmp_path / "workspace"
    storage = _RecordingStorage()
    migrated = workspace / "plugin-data" / "default_memory" / "config.local.toml"
    migrated.parent.mkdir(parents=True)
    migrated.write_text('db_path = "migrated.db"\n', encoding="utf-8")

    cfg = load_default_memory_config(workspace=workspace, storage=storage)
    ensure_default_memory_config_file(workspace=workspace, storage=storage)

    backend_dir = Path(config_module.__file__).resolve().parent
    assert cfg.db_path == "migrated.db"
    assert storage.calls == [
        {
            "plugin_id": "default_memory",
            "plugin_dir": backend_dir,
            "workspace": workspace,
        },
        {
            "plugin_id": "default_memory",
            "plugin_dir": backend_dir,
            "workspace": workspace,
            "default_text": render_default_memory_config(),
        },
    ]


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
