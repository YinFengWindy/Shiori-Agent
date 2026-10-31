"""Proactive host settings move once, and the dead ``[proactive]`` section is deleted."""

from __future__ import annotations

import logging
import tomllib
from pathlib import Path

import pytest

from agent.config import load_config
from bootstrap.proactive_config_migration import migrate_legacy_proactive_config


def _migrate(tmp_path: Path, text: str) -> dict:
    path = tmp_path / "config.toml"
    path.write_text(text, encoding="utf-8")
    migrate_legacy_proactive_config(path)
    return tomllib.loads(path.read_text(encoding="utf-8"))


def test_disabled_switches_move_and_the_legacy_tables_are_deleted(
    tmp_path: Path,
) -> None:
    document = _migrate(
        tmp_path,
        """
[agent]
max_tokens = 8

[agent.proactive_strategies]
scene_followup = false
relationship = false

[proactive]
enabled = false
profile = "quiet"

[plugins.proactive]
label = "keep"
""",
    )

    assert document["agent"] == {"max_tokens": 8}
    assert "proactive" not in document
    assert document["plugins"]["proactive"] == {
        "label": "keep",
        "scene_followup": False,
        "relationship": False,
    }


def test_the_dead_section_is_deleted_without_copying_its_values(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    path = tmp_path / "config.toml"
    path.write_text(
        '[proactive]\nenabled = false\nprofile = "quiet"\n\n'
        "[proactive.agent]\nmax_steps = 4\n\n"
        "[agent]\nmax_tokens = 8\n",
        encoding="utf-8",
    )

    with caplog.at_level(logging.INFO):
        migrate_legacy_proactive_config(path)

    assert tomllib.loads(path.read_text(encoding="utf-8")) == {
        "agent": {"max_tokens": 8}
    }
    assert f"{path} 的 [proactive] 段没有运行时消费方，已删除" in caplog.text


def test_default_switches_leave_no_plugin_keys(tmp_path: Path) -> None:
    document = _migrate(
        tmp_path,
        "[agent.proactive_strategies]\n"
        "scene_followup = true\n"
        "relationship = true\n",
    )

    assert document == {}


def test_values_the_plugin_already_has_are_kept(tmp_path: Path) -> None:
    document = _migrate(
        tmp_path,
        """
[agent.proactive_strategies]
scene_followup = false
relationship = false

[plugins.proactive]
scene_followup = true
enabled = false
""",
    )

    assert "agent" not in document
    assert document["plugins"]["proactive"] == {
        "scene_followup": True,
        "enabled": False,
        "relationship": False,
    }


def test_a_second_run_leaves_the_migrated_file_unchanged(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    path = tmp_path / "config.toml"
    path.write_text(
        "[agent.proactive_strategies]\nscene_followup = false\n"
        "[proactive]\nenabled = false\n",
        encoding="utf-8",
    )
    migrate_legacy_proactive_config(path)
    migrated = path.read_bytes()
    caplog.clear()

    with caplog.at_level(logging.INFO):
        migrate_legacy_proactive_config(path)

    assert path.read_bytes() == migrated
    assert caplog.text == ""
    assert tomllib.loads(migrated.decode()) == {
        "plugins": {"proactive": {"scene_followup": False}}
    }


def test_an_inline_legacy_table_raises_and_leaves_the_file(tmp_path: Path) -> None:
    path = tmp_path / "config.toml"
    original = "agent = { proactive_strategies = { scene_followup = false } }\n"
    path.write_text(original, encoding="utf-8")

    with pytest.raises(ValueError, match="内联表"):
        migrate_legacy_proactive_config(path)

    assert path.read_text(encoding="utf-8") == original


def test_an_inline_proactive_section_raises_and_leaves_the_file(tmp_path: Path) -> None:
    path = tmp_path / "config.toml"
    original = 'proactive = { enabled = false, profile = "quiet" }\n'
    path.write_text(original, encoding="utf-8")

    with pytest.raises(ValueError, match="内联表"):
        migrate_legacy_proactive_config(path)

    assert path.read_text(encoding="utf-8") == original


def test_an_inline_plugin_table_raises_and_leaves_the_file(tmp_path: Path) -> None:
    path = tmp_path / "config.toml"
    original = (
        'plugins = { proactive = { label = "keep" } }\n\n'
        "[agent.proactive_strategies]\nrelationship = false\n"
    )
    path.write_text(original, encoding="utf-8")

    with pytest.raises(ValueError, match="内联表"):
        migrate_legacy_proactive_config(path)

    assert path.read_text(encoding="utf-8") == original


def test_unknown_strategy_keys_raise_and_leave_the_file(tmp_path: Path) -> None:
    path = tmp_path / "config.toml"
    original = "[agent.proactive_strategies]\nscene_followup = false\nextra = 1\n"
    path.write_text(original, encoding="utf-8")

    with pytest.raises(ValueError, match="只能有 scene_followup"):
        migrate_legacy_proactive_config(path)

    assert path.read_text(encoding="utf-8") == original


def test_a_non_boolean_switch_raises_and_leaves_the_file(tmp_path: Path) -> None:
    path = tmp_path / "config.toml"
    original = '[agent.proactive_strategies]\nrelationship = "false"\n'
    path.write_text(original, encoding="utf-8")

    with pytest.raises(ValueError, match="必须是布尔值"):
        migrate_legacy_proactive_config(path)

    assert path.read_text(encoding="utf-8") == original


def test_load_config_applies_the_migration(tmp_path: Path) -> None:
    path = tmp_path / "config.toml"
    path.write_text(
        "[plugins.default_memory]\nenabled = true\n\n"
        '[proactive]\nenabled = false\nprofile = "quiet"\n\n'
        "[agent.proactive_strategies]\nrelationship = false\n",
        encoding="utf-8",
    )

    config = load_config(path)
    migrated = path.read_bytes()

    assert tomllib.loads(migrated.decode()) == {
        "plugins": {
            "default_memory": {"enabled": True},
            "proactive": {"relationship": False},
        }
    }
    assert config.plugins["proactive"]["relationship"] is False
    load_config(path)
    assert path.read_bytes() == migrated
