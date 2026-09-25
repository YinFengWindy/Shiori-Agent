"""默认停用的内置插件：新安装按 manifest 默认停用，升级用户保留启用。"""

from __future__ import annotations

import shutil
import tomllib
from pathlib import Path

import pytest

from agent.config import load_config
from agent.plugin_default_enabled_migration import (
    DEFAULT_DISABLED_PLUGINS,
    RECEIPT_KEY,
)
from bootstrap.paths import REPOSITORY_ROOT

_TEMPLATE = REPOSITORY_ROOT / "config" / "examples" / "config.example.toml"


@pytest.fixture(autouse=True)
def _without_proactive_target_receipt(monkeypatch: pytest.MonkeyPatch) -> None:
    """本文件只测自己的迁移：停掉全局主动推送目标的升级迁移，免得它写入自己的回执。"""
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


def _write(tmp_path: Path, extra: str = "") -> Path:
    path = tmp_path / "config.toml"
    path.write_text(_BASE + extra, encoding="utf-8")
    return path


def _persisted(path: Path) -> dict:
    return tomllib.loads(path.read_text(encoding="utf-8"))


def test_fresh_config_from_the_template_is_not_rewritten(tmp_path: Path) -> None:
    """新安装复制模板：模板自带回执，插件不被显式启用。"""
    path = tmp_path / "config.toml"
    shutil.copyfile(_TEMPLATE, path)
    before = path.read_text(encoding="utf-8")

    config = load_config(path)

    assert path.read_text(encoding="utf-8") == before
    for plugin_id in DEFAULT_DISABLED_PLUGINS:
        assert "enabled" not in config.plugins.get(plugin_id, {})
    receipt = _persisted(path)["_migrations"][RECEIPT_KEY]
    assert receipt == list(DEFAULT_DISABLED_PLUGINS)


def test_existing_config_pins_the_plugins_enabled_once(tmp_path: Path) -> None:
    """升级前缺省即启用：没有显式 enabled 的旧配置写成 enabled = true。"""
    path = _write(tmp_path)

    config = load_config(path)

    persisted = _persisted(path)
    for plugin_id in DEFAULT_DISABLED_PLUGINS:
        assert persisted["plugins"][plugin_id] == {"enabled": True}
        assert config.plugins[plugin_id]["enabled"] is True
    assert persisted["_migrations"][RECEIPT_KEY] == list(DEFAULT_DISABLED_PLUGINS)
    assert "# 用户自己的注释要保留" in path.read_text(encoding="utf-8")

    # 已有回执：第二次加载不再改写，删掉 enabled 之后按 manifest 默认值处理。
    after_first = path.read_text(encoding="utf-8")
    _ = load_config(path)
    assert path.read_text(encoding="utf-8") == after_first


def test_explicit_settings_are_kept_and_other_keys_survive(tmp_path: Path) -> None:
    path = _write(
        tmp_path,
        "\n[plugins.browser_use]\nenabled = false\n"
        '\n[plugins.computer_use]\nsome_setting = "kept"\n'
        '\n[_migrations]\nplugin_config_json = ["demo"]\n',
    )

    _ = load_config(path)

    persisted = _persisted(path)
    assert persisted["plugins"]["browser_use"] == {"enabled": False}
    assert persisted["plugins"]["computer_use"] == {
        "some_setting": "kept",
        "enabled": True,
    }
    assert persisted["_migrations"] == {
        "plugin_config_json": ["demo"],
        RECEIPT_KEY: list(DEFAULT_DISABLED_PLUGINS),
    }


def test_only_plugins_missing_from_the_receipt_are_migrated(tmp_path: Path) -> None:
    """回执里已有的插件不再迁移，只处理后来才改成默认停用的插件。"""
    path = _write(tmp_path, f'\n[_migrations]\n{RECEIPT_KEY} = ["browser_use"]\n')

    _ = load_config(path)

    persisted = _persisted(path)
    assert "browser_use" not in persisted.get("plugins", {})
    assert persisted["plugins"]["computer_use"] == {"enabled": True}
    assert persisted["_migrations"][RECEIPT_KEY] == ["browser_use", "computer_use"]
