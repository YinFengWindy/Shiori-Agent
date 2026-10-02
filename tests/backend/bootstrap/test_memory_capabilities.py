from __future__ import annotations

import tomllib
from pathlib import Path
from types import SimpleNamespace

import pytest
from bootstrap.memory_capabilities import HostMemoryStorage


def load_default_memory_config(*, plugin_dir=None, workspace=None, storage=None):
    path = (storage or HostMemoryStorage()).resolve_config(
        plugin_id="default_memory",
        plugin_dir=plugin_dir or Path("unused"),
        workspace=workspace,
    )
    payload = tomllib.loads(path.read_text(encoding="utf-8"))
    return SimpleNamespace(
        db_path=payload["db_path"],
        retrieval=SimpleNamespace(
            top_k_history=payload.get("retrieval", {}).get("top_k_history", 8)
        ),
    )


def ensure_default_memory_config_file(*, plugin_dir=None, workspace=None, storage=None):
    return (storage or HostMemoryStorage()).resolve_config(
        plugin_id="default_memory",
        plugin_dir=plugin_dir or Path("unused"),
        workspace=workspace,
        default_text='db_path = ""',
    )


def test_workspace_legacy_config_migrates_and_wins(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    legacy = workspace / "plugins" / "default_memory" / "config.local.toml"
    legacy.parent.mkdir(parents=True)
    legacy.write_text('db_path = "legacy.db"\n', encoding="utf-8")

    cfg = load_default_memory_config(workspace=workspace, storage=HostMemoryStorage())

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

    cfg = load_default_memory_config(workspace=workspace, storage=HostMemoryStorage())

    assert cfg.db_path == "current.db"
    assert legacy.exists()


def test_clean_workspace_creates_editable_defaults_in_data_directory(
    tmp_path: Path,
) -> None:
    workspace = tmp_path / "workspace"
    path = ensure_default_memory_config_file(
        workspace=workspace, storage=HostMemoryStorage()
    )

    assert path.name == "config.local.toml"
    assert path == workspace / "plugin-data" / "default_memory" / "config.local.toml"
    assert path.is_file()


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
    cfg = load_default_memory_config(
        plugin_dir=package, workspace=workspace, storage=HostMemoryStorage()
    )
    assert cfg.db_path == "user.db"
    assert cfg.retrieval.top_k_history == 21
    target = ensure_default_memory_config_file(
        plugin_dir=package, workspace=workspace, storage=HostMemoryStorage()
    )
    assert target == workspace / "plugin-data/default_memory/config.local.toml"
    assert not source.exists()
    package.mkdir(parents=True, exist_ok=True)
    (package / "config.local.toml").write_text(
        'db_path = "replacement.db"\n', encoding="utf-8"
    )
    assert (
        load_default_memory_config(
            plugin_dir=package, workspace=workspace, storage=HostMemoryStorage()
        )
        == cfg
    )
