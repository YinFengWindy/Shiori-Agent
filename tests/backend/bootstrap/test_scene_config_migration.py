"""``[agent.scene_observation]`` moves once into ``[plugins.scene]``."""

from __future__ import annotations

import tomllib
from pathlib import Path

import pytest

from bootstrap.scene_config_migration import migrate_legacy_scene_config


def _write(path: Path, text: str) -> None:
    path.write_text(text, encoding="utf-8")


def _document(path: Path) -> dict:
    return tomllib.loads(path.read_text(encoding="utf-8"))


def test_missing_plugin_key_is_copied_and_the_legacy_table_is_deleted(
    tmp_path: Path,
) -> None:
    path = tmp_path / "config.toml"
    _write(
        path,
        """
[agent]
max_tokens = 8

[agent.scene_observation]
enabled = false

[plugins.scene]
enabled = true
label = "keep"
""",
    )

    migrate_legacy_scene_config(path)

    document = _document(path)
    assert "scene_observation" not in document["agent"]
    assert document["agent"]["max_tokens"] == 8
    assert document["plugins"]["scene"] == {
        "enabled": True,
        "label": "keep",
        "observation_enabled": False,
    }


def test_existing_plugin_key_is_kept_and_the_legacy_table_is_still_deleted(
    tmp_path: Path,
) -> None:
    path = tmp_path / "config.toml"
    _write(
        path,
        """
[agent.scene_observation]
enabled = false

[plugins.scene]
enabled = true
observation_enabled = true
""",
    )

    migrate_legacy_scene_config(path)

    scene = _document(path)["plugins"]["scene"]
    assert scene["observation_enabled"] is True
    assert scene["enabled"] is True
    assert "scene_observation" not in _document(path).get("agent", {})


def test_omitted_legacy_enabled_is_written_as_true(tmp_path: Path) -> None:
    path = tmp_path / "config.toml"
    _write(path, "[agent.scene_observation]\n")

    migrate_legacy_scene_config(path)

    assert _document(path)["plugins"]["scene"]["observation_enabled"] is True
    assert "agent" not in _document(path) or "scene_observation" not in _document(
        path
    ).get("agent", {})


def test_neither_table_is_a_no_op(tmp_path: Path) -> None:
    path = tmp_path / "config.toml"
    original = "[agent]\nmax_tokens = 8\n"
    _write(path, original)

    migrate_legacy_scene_config(path)

    assert path.read_text(encoding="utf-8") == original


def test_a_second_run_leaves_the_migrated_file_unchanged(tmp_path: Path) -> None:
    path = tmp_path / "config.toml"
    _write(path, "[agent.scene_observation]\nenabled = false\n")
    migrate_legacy_scene_config(path)
    migrated = path.read_text(encoding="utf-8")

    migrate_legacy_scene_config(path)

    assert path.read_text(encoding="utf-8") == migrated
    assert _document(path)["plugins"]["scene"]["observation_enabled"] is False


def test_an_inline_legacy_table_raises_and_leaves_the_file(tmp_path: Path) -> None:
    path = tmp_path / "config.toml"
    original = "agent = { scene_observation = { enabled = false }, max_tokens = 8 }\n"
    _write(path, original)

    with pytest.raises(ValueError, match="内联表"):
        migrate_legacy_scene_config(path)

    assert path.read_text(encoding="utf-8") == original
