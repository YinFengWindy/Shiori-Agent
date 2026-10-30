"""The memory optimizer settings move once into ``[plugins.memory_optimizer]``."""

from __future__ import annotations

import tomllib
from pathlib import Path

import pytest

from bootstrap.memory_optimizer_config_migration import (
    migrate_legacy_memory_optimizer_config,
)


def _migrate(tmp_path: Path, text: str) -> dict:
    path = tmp_path / "config.toml"
    path.write_text(text, encoding="utf-8")
    migrate_legacy_memory_optimizer_config(path)
    return tomllib.loads(path.read_text(encoding="utf-8"))


def test_disabled_switch_and_interval_move_and_the_legacy_table_is_deleted(
    tmp_path: Path,
) -> None:
    document = _migrate(
        tmp_path,
        """
[agent]
max_tokens = 8

[agent.maintenance]
memory_optimizer_enabled = false
memory_optimizer_interval_seconds = 30

[plugins.memory_optimizer]
label = "keep"
""",
    )

    assert document["agent"] == {"max_tokens": 8}
    # Below the old minimum of 60, as the old loop clamped it.
    assert document["plugins"]["memory_optimizer"] == {
        "label": "keep",
        "enabled": False,
        "interval_seconds": 60,
    }


def test_top_level_keys_are_the_fallback_and_are_deleted(tmp_path: Path) -> None:
    document = _migrate(
        tmp_path,
        "memory_optimizer_enabled = false\n"
        "memory_optimizer_interval_seconds = 3600\n"
        "max_tokens = 8\n"
        "\n[agent.maintenance]\nmemory_optimizer_interval_seconds = 7200\n",
    )

    assert document == {
        "max_tokens": 8,
        "plugins": {
            "memory_optimizer": {"enabled": False, "interval_seconds": 7200},
        },
    }


def test_values_the_plugin_already_has_are_kept(tmp_path: Path) -> None:
    document = _migrate(
        tmp_path,
        """
[agent.maintenance]
memory_optimizer_enabled = false
memory_optimizer_interval_seconds = 3600

[plugins.memory_optimizer]
enabled = true
interval_seconds = 120
""",
    )

    assert "agent" not in document
    assert document["plugins"]["memory_optimizer"] == {
        "enabled": True,
        "interval_seconds": 120,
    }


def test_default_values_leave_no_plugin_table(tmp_path: Path) -> None:
    document = _migrate(
        tmp_path,
        "[agent.maintenance]\n"
        "memory_optimizer_enabled = true\n"
        "memory_optimizer_interval_seconds = 64800\n",
    )

    assert document == {}


def test_a_second_run_leaves_the_migrated_file_unchanged(tmp_path: Path) -> None:
    path = tmp_path / "config.toml"
    path.write_text(
        "[agent.maintenance]\nmemory_optimizer_enabled = false\n", encoding="utf-8"
    )
    migrate_legacy_memory_optimizer_config(path)
    migrated = path.read_text(encoding="utf-8")

    migrate_legacy_memory_optimizer_config(path)

    assert path.read_text(encoding="utf-8") == migrated
    assert tomllib.loads(migrated) == {
        "plugins": {"memory_optimizer": {"enabled": False}}
    }


def test_an_inline_legacy_table_raises_and_leaves_the_file(tmp_path: Path) -> None:
    path = tmp_path / "config.toml"
    original = "agent = { maintenance = { memory_optimizer_enabled = false } }\n"
    path.write_text(original, encoding="utf-8")

    with pytest.raises(ValueError, match="内联表"):
        migrate_legacy_memory_optimizer_config(path)

    assert path.read_text(encoding="utf-8") == original
