"""Host memory storage resolves memory-plugin config through the local-config owner.

How ``default_memory`` parses the resolved file is asserted in
``plugins/default_memory/tests/test_config.py``; this file covers the host side:
every legacy layout migrates once into ``plugin-data`` and later package files
never shadow the migrated workspace copy.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from bootstrap.memory_capabilities import HostMemoryStorage

_USER_CONFIG = 'db_path = "user.db"\n[retrieval]\ntop_k_history = 21\n'


def _resolve(storage: HostMemoryStorage, package: Path, workspace: Path, **kwargs):
    return storage.resolve_config(
        plugin_id="default_memory", plugin_dir=package, workspace=workspace, **kwargs
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
    source.write_text(_USER_CONFIG, encoding="utf-8")
    storage = HostMemoryStorage()
    target = workspace / "plugin-data/default_memory/config.local.toml"

    assert _resolve(storage, package, workspace) == target
    assert target.read_text(encoding="utf-8") == _USER_CONFIG
    assert not source.exists()
    assert _resolve(storage, package, workspace, default_text="defaults") == target
    package.mkdir(parents=True, exist_ok=True)
    (package / "config.local.toml").write_text(
        'db_path = "replacement.db"\n', encoding="utf-8"
    )
    assert _resolve(storage, package, workspace) == target
    assert target.read_text(encoding="utf-8") == _USER_CONFIG


def test_workspace_config_is_preserved_when_legacy_also_exists(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    target = workspace / "plugin-data" / "default_memory" / "config.local.toml"
    target.parent.mkdir(parents=True)
    target.write_text('db_path = "current.db"\n', encoding="utf-8")
    legacy = workspace / "plugins" / "default_memory" / "config.local.toml"
    legacy.parent.mkdir(parents=True)
    legacy.write_text('db_path = "old.db"\n', encoding="utf-8")

    resolved = _resolve(HostMemoryStorage(), tmp_path / "package", workspace)

    assert resolved == target
    assert target.read_text(encoding="utf-8") == 'db_path = "current.db"\n'
    assert legacy.exists()
