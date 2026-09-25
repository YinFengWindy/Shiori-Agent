"""渠道插件配置里的 allow_from 白名单一次性删除（#398）。"""

from __future__ import annotations

import tomllib
from pathlib import Path
from typing import Any

import pytest

from agent.channel_allowlist_migration import remove_channel_allowlists
from agent.config import load_config


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
[agent]
max_tokens = 4096
"""


def _write(tmp_path: Path, extra: str) -> Path:
    path = tmp_path / "config.toml"
    _ = path.write_text(_BASE + extra, encoding="utf-8")
    return path


def _migrate(path: Path) -> dict[str, Any]:
    return remove_channel_allowlists(
        path, tomllib.loads(path.read_text(encoding="utf-8"))
    )


def test_allow_from_is_deleted_from_every_channel_plugin_table(tmp_path: Path) -> None:
    path = _write(
        tmp_path,
        """
[plugins.telegram]
token = "123:abc"
allow_from = ["alice"]

[plugins.qq]
bot_uin = "10001"
allow_from = ["42"]

[plugins.qqbot]
app_id = "app"
client_secret = "${QQBOT_SECRET}"
allow_from = ["openid"]

[[plugins.qqbot.groups]]
group_openid = "g1"
allowFrom = ["member"]
require_at = true
""",
    )

    migrated = _migrate(path)

    persisted = tomllib.loads(path.read_text(encoding="utf-8"))
    assert persisted == migrated
    assert persisted["plugins"] == {
        "telegram": {"token": "123:abc"},
        "qq": {"bot_uin": "10001"},
        # The ${ENV} placeholder is carried verbatim, never resolved into the file.
        "qqbot": {
            "app_id": "app",
            "client_secret": "${QQBOT_SECRET}",
            "groups": [{"group_openid": "g1", "require_at": True}],
        },
    }
    assert "# 用户自己的注释要保留" in path.read_text(encoding="utf-8")


def test_config_without_allow_from_is_left_untouched(tmp_path: Path) -> None:
    path = _write(tmp_path, '\n[plugins.qq]\nbot_uin = "10001"\n')
    before = path.read_text(encoding="utf-8")
    data = tomllib.loads(before)

    assert remove_channel_allowlists(path, data) is data
    assert path.read_text(encoding="utf-8") == before


def test_other_plugins_keep_their_allow_from(tmp_path: Path) -> None:
    path = _write(tmp_path, '\n[plugins.custom]\nallow_from = ["x"]\n')
    before = path.read_text(encoding="utf-8")

    _ = _migrate(path)

    assert path.read_text(encoding="utf-8") == before


def test_load_config_removes_allow_from_once(tmp_path: Path) -> None:
    path = _write(tmp_path, '\n[plugins.qq]\nbot_uin = "10001"\nallow_from = ["42"]\n')

    config = load_config(path)
    after_first = path.read_text(encoding="utf-8")
    _ = load_config(path)

    assert config.plugins["qq"] == {"bot_uin": "10001"}
    assert "allow_from" not in after_first
    assert path.read_text(encoding="utf-8") == after_first
