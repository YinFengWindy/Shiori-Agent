"""[channels.telegram] → [plugins.telegram] 一次性迁移与旧表拒绝（#363 T4）。"""

from __future__ import annotations

import logging
import tomllib
from pathlib import Path

import pytest

from agent.config import load_config, load_config_text


@pytest.fixture(autouse=True)
def _without_default_disabled_pinning(monkeypatch):
    """本文件只测自己的迁移：停掉默认停用插件与全局主动推送目标的升级迁移，免得它们改写测试配置。"""
    monkeypatch.setattr(
        "agent.plugin_default_enabled_migration.DEFAULT_DISABLED_PLUGINS", ()
    )
    monkeypatch.setattr(
        "agent.proactive_target_migration.remove_proactive_target",
        lambda _path, data: data,
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
    path.write_text(_BASE + extra, encoding="utf-8")
    return path


def _persisted(path: Path) -> dict:
    return tomllib.loads(path.read_text(encoding="utf-8"))


def test_fresh_config_is_left_untouched(tmp_path: Path) -> None:
    path = _write(tmp_path, "")
    before = path.read_text(encoding="utf-8")

    config = load_config(path)

    assert path.read_text(encoding="utf-8") == before
    assert "telegram" not in config.plugins


def test_old_table_moves_into_plugin_table_and_is_deleted(tmp_path: Path) -> None:
    path = _write(
        tmp_path,
        """
[channels.telegram]
token = "123:abc"
channel_name = "telegram"

[memory]
enabled = false
""",
    )

    config = load_config(path)

    text = path.read_text(encoding="utf-8")
    persisted = tomllib.loads(text)
    assert "channels" not in persisted or "telegram" not in persisted["channels"]
    assert persisted["plugins"]["telegram"] == {"token": "123:abc"}
    assert persisted["memory"] == {"enabled": False}
    assert "# 用户自己的注释要保留" in text
    assert config.plugins["telegram"] == {"token": "123:abc"}


def test_env_placeholder_is_carried_verbatim(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("TG_TOKEN", "resolved-secret")
    path = _write(tmp_path, '\n[channels.telegram]\ntoken = "${TG_TOKEN}"\n')

    config = load_config(path)

    text = path.read_text(encoding="utf-8")
    assert "resolved-secret" not in text
    assert _persisted(path)["plugins"]["telegram"] == {"token": "${TG_TOKEN}"}
    assert config.plugins["telegram"]["token"] == "resolved-secret"


def test_disabled_old_table_disables_the_plugin(tmp_path: Path) -> None:
    path = _write(
        tmp_path, '\n[channels.telegram]\ntoken = "123:abc"\nenabled = false\n'
    )

    load_config(path)

    assert _persisted(path)["plugins"]["telegram"] == {
        "token": "123:abc",
        "enabled": False,
    }


def test_existing_plugin_enabled_flag_is_preserved(tmp_path: Path) -> None:
    path = _write(
        tmp_path,
        """
[channels.telegram]
token = "123:abc"
enabled = false

[plugins.telegram]
enabled = true
""",
    )

    load_config(path)

    assert _persisted(path)["plugins"]["telegram"] == {
        "token": "123:abc",
        "enabled": True,
    }


def test_configured_plugin_table_wins_over_old_table(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    path = _write(
        tmp_path,
        """
[channels.telegram]
token = "old-token"

[plugins.telegram]
token = "plugin-token"
""",
    )

    with caplog.at_level(logging.WARNING, logger="agent.channel_config_migration"):
        config = load_config(path)

    persisted = _persisted(path)
    assert "telegram" not in persisted.get("channels", {})
    assert persisted["plugins"]["telegram"] == {"token": "plugin-token"}
    assert config.plugins["telegram"]["token"] == "plugin-token"
    assert "[plugins.telegram] 已有配置" in caplog.text


def test_empty_old_table_written_by_desktop_is_dropped(tmp_path: Path) -> None:
    # 旧版桌面端每次保存都会写出这样一张空表。
    path = _write(
        tmp_path, '\n[channels.telegram]\ntoken = ""\nchannel_name = "telegram"\n'
    )

    config = load_config(path)

    persisted = _persisted(path)
    assert "telegram" not in persisted.get("channels", {})
    assert "telegram" not in persisted.get("plugins", {})
    assert "telegram" not in config.plugins


def test_custom_channel_name_is_dropped_with_warning(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    path = _write(
        tmp_path,
        '\n[channels.telegram]\ntoken = "123:abc"\nchannel_name = "telegram_work"\n',
    )

    with caplog.at_level(logging.WARNING, logger="agent.channel_config_migration"):
        load_config(path)

    assert _persisted(path)["plugins"]["telegram"] == {"token": "123:abc"}
    assert "telegram_work" in caplog.text


def test_inline_old_table_falls_back_to_structural_rewrite(tmp_path: Path) -> None:
    path = _write(tmp_path, '\n[channels]\ntelegram = { token = "123:abc" }\n')

    load_config(path)

    persisted = _persisted(path)
    assert "telegram" not in persisted.get("channels", {})
    assert persisted["plugins"]["telegram"] == {"token": "123:abc"}
    assert persisted["agent"]["max_tokens"] == 4096


def test_migration_is_idempotent(tmp_path: Path) -> None:
    path = _write(tmp_path, '\n[channels.telegram]\ntoken = "123:abc"\n')
    load_config(path)
    migrated = path.read_text(encoding="utf-8")

    load_config(path)

    assert path.read_text(encoding="utf-8") == migrated


def test_reappearing_non_empty_old_table_is_rejected() -> None:
    # runtime.apply 走 load_config_text，不迁移；旧渲染端或手改 TOML 写回旧表时报错。
    with pytest.raises(
        ValueError, match=r"配置项已迁移: \[channels.telegram\] → \[plugins.telegram\]"
    ):
        load_config_text(_BASE + '\n[channels.telegram]\ntoken = "123:abc"\n')


def test_reappearing_empty_old_table_is_ignored() -> None:
    config = load_config_text(
        _BASE + '\n[channels.telegram]\ntoken = ""\nchannel_name = "telegram"\n'
    )

    assert "telegram" not in config.plugins


# ── QQ（NapCat）：#363 T5 ─────────────────────────────────────────────


def test_qq_table_moves_with_timeout_and_drops_legacy_keys(tmp_path: Path) -> None:
    path = _write(
        tmp_path,
        """
[channels.qq]
bot_uin = 10001
websocket_open_timeout_seconds = 9.5
allow_from = ["42"]

[[channels.qq.groups]]
group_id = "123"
""",
    )

    config = load_config(path)

    persisted = _persisted(path)
    assert "channels" not in persisted or "qq" not in persisted["channels"]
    assert persisted["plugins"]["qq"] == {
        "bot_uin": 10001,
        "websocket_open_timeout_seconds": 9.5,
    }
    assert config.plugins["qq"]["bot_uin"] == 10001


def test_both_builtin_tables_migrate_in_one_pass(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("QQ_UIN", "10001")
    # 旧版桌面端的完整写回：两张表都在，其中 QQ 带 enabled = false。
    path = _write(
        tmp_path,
        """
[channels.telegram]
token = "123:abc"
channel_name = "telegram"

[channels.qq]
bot_uin = "${QQ_UIN}"
websocket_open_timeout_seconds = 5
enabled = false
""",
    )

    config = load_config(path)

    persisted = _persisted(path)
    assert "channels" not in persisted or not persisted["channels"]
    assert persisted["plugins"]["telegram"] == {"token": "123:abc"}
    assert persisted["plugins"]["qq"] == {
        "bot_uin": "${QQ_UIN}",
        "websocket_open_timeout_seconds": 5,
        "enabled": False,
    }
    assert config.plugins["qq"]["bot_uin"] == "10001"


def test_empty_qq_table_written_by_desktop_is_dropped(tmp_path: Path) -> None:
    path = _write(
        tmp_path,
        '\n[channels.qq]\nbot_uin = ""\nwebsocket_open_timeout_seconds = 5\n',
    )

    config = load_config(path)

    persisted = _persisted(path)
    assert "qq" not in persisted.get("channels", {})
    assert "qq" not in persisted.get("plugins", {})
    assert "qq" not in config.plugins


def test_qqbot_table_is_not_mistaken_for_qq() -> None:
    # [channels.qqbot] 早已移除，仍按「已移除」报错，不能被 qq 的迁移吞掉。
    with pytest.raises(ValueError, match=r"配置项已移除: \[channels.qqbot\]"):
        load_config_text(_BASE + '\n[channels.qqbot]\napp_id = "x"\n')


def test_reappearing_non_empty_qq_table_is_rejected() -> None:
    with pytest.raises(
        ValueError, match=r"配置项已迁移: \[channels.qq\] → \[plugins.qq\]"
    ):
        load_config_text(_BASE + '\n[channels.qq]\nbot_uin = "10001"\n')
    config = load_config_text(_BASE + '\n[channels.qq]\nbot_uin = ""\n')
    assert "qq" not in config.plugins
