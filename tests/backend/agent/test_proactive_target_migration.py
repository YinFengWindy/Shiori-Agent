"""[proactive] 全局投递目标一次性删除（#399）。"""

from __future__ import annotations

import logging
import tomllib
from pathlib import Path
from typing import Any

import pytest

from agent.config import load_config, load_config_text
from agent.proactive_target_migration import remove_proactive_target


@pytest.fixture(autouse=True)
def _without_default_disabled_pinning(monkeypatch: pytest.MonkeyPatch) -> None:
    """本文件只测自己的迁移：停掉默认停用插件的升级迁移，免得它改写测试配置。"""
    monkeypatch.setattr(
        "agent.plugin_default_enabled_migration.DEFAULT_DISABLED_PLUGINS", ()
    )


_BASE = """
[llm]
registrations = []

# 用户自己的注释要保留
[proactive]
enabled = true
profile = "quiet"
"""


def _write(tmp_path: Path, extra: str) -> Path:
    path = tmp_path / "config.toml"
    _ = path.write_text(_BASE + extra, encoding="utf-8")
    return path


def _migrate(path: Path) -> dict[str, Any]:
    return remove_proactive_target(
        path, tomllib.loads(path.read_text(encoding="utf-8"))
    )


def test_target_table_and_root_keys_are_deleted_keeping_comments(
    tmp_path: Path,
) -> None:
    path = _write(
        tmp_path,
        """default_channel = "qq"
default_chat_id = "7"
default_role_id = "mira"

[proactive.target]
channel = "telegram"
chat_id = "1"

[proactive.agent]
# 后面的表不受影响
max_steps = 12
""",
    )

    migrated = _migrate(path)

    text = path.read_text(encoding="utf-8")
    assert tomllib.loads(text) == migrated
    assert migrated["proactive"] == {
        "enabled": True,
        "profile": "quiet",
        "agent": {"max_steps": 12},
    }
    assert "# 用户自己的注释要保留" in text
    assert "# 后面的表不受影响" in text


def test_inline_target_is_deleted(tmp_path: Path) -> None:
    path = _write(tmp_path, 'target = { channel = "telegram", chat_id = "1" }\n')

    migrated = _migrate(path)

    assert migrated["proactive"] == {"enabled": True, "profile": "quiet"}
    assert "# 用户自己的注释要保留" in path.read_text(encoding="utf-8")


def test_dotted_target_falls_back_to_a_full_rewrite(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    path = tmp_path / "config.toml"
    _ = path.write_text(
        '[proactive]\nprofile = "quiet"\ntarget.channel = "telegram"\n',
        encoding="utf-8",
    )

    with caplog.at_level(logging.WARNING, logger="agent.config_migration_writer"):
        migrated = _migrate(path)

    assert migrated == {"proactive": {"profile": "quiet"}}
    assert tomllib.loads(path.read_text(encoding="utf-8")) == migrated
    assert "改为整体重写" in caplog.text


def test_config_without_a_global_target_is_left_untouched(tmp_path: Path) -> None:
    path = _write(tmp_path, "")
    before = path.read_text(encoding="utf-8")
    data = tomllib.loads(before)

    assert remove_proactive_target(path, data) is data
    assert path.read_text(encoding="utf-8") == before


def test_load_config_removes_the_target_once(tmp_path: Path) -> None:
    path = _write(tmp_path, '\n[proactive.target]\nchannel = "telegram"\n')

    config = load_config(path)
    after_first = path.read_text(encoding="utf-8")
    _ = load_config(path)

    assert config.proactive.enabled is True
    assert config.proactive.role_id == ""
    assert "target" not in after_first
    assert path.read_text(encoding="utf-8") == after_first


def test_a_reappearing_target_is_rejected_without_migration() -> None:
    with pytest.raises(ValueError, match="配置项已移除: target"):
        load_config_text(_BASE + '\n[proactive.target]\nchannel = "telegram"\n')
