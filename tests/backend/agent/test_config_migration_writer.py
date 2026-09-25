"""配置迁移的共享写回：能拼接就保留注释，拼不出来就整体重写。"""

from __future__ import annotations

import tomllib
from pathlib import Path

from agent.config_migration_writer import save_migrated_config
from desktop_bridge.plugin_config_text import PluginTableConflict

_ORIGINAL = """# 用户注释
[plugins.qq]
bot_uin = "1"
allow_from = ["42"]
"""
_MIGRATED = {"plugins": {"qq": {"bot_uin": "1"}}}


def _config(tmp_path: Path, text: str = _ORIGINAL) -> Path:
    path = tmp_path / "config.toml"
    _ = path.write_text(text, encoding="utf-8")
    return path


def test_spliced_text_is_kept_with_its_comments(tmp_path: Path) -> None:
    path = _config(tmp_path)

    result = save_migrated_config(
        path, _MIGRATED, lambda text: text.replace('allow_from = ["42"]\n', "")
    )

    assert result == _MIGRATED
    assert path.read_text(encoding="utf-8").startswith("# 用户注释")


def test_unlocatable_splice_falls_back_to_a_full_rewrite(tmp_path: Path) -> None:
    path = _config(tmp_path)

    def conflict(_text: str) -> str:
        raise PluginTableConflict("qq")

    result = save_migrated_config(path, _MIGRATED, conflict)

    assert result == _MIGRATED
    assert tomllib.loads(path.read_text(encoding="utf-8")) == _MIGRATED
    assert "# 用户注释" not in path.read_text(encoding="utf-8")


def test_splice_that_misses_the_result_falls_back(tmp_path: Path) -> None:
    path = _config(tmp_path)

    result = save_migrated_config(path, _MIGRATED, lambda text: text)

    assert result == _MIGRATED


def test_unparseable_splice_falls_back(tmp_path: Path) -> None:
    path = _config(tmp_path)

    result = save_migrated_config(path, _MIGRATED, lambda text: text + "[[broken")

    assert result == _MIGRATED


def test_custom_completeness_check_accepts_a_partial_equal_result(
    tmp_path: Path,
) -> None:
    path = _config(tmp_path)
    # The structural result keeps an empty parent table the text never had.
    migrated = {**_MIGRATED, "channels": {}}

    result = save_migrated_config(
        path,
        migrated,
        lambda text: text.replace('allow_from = ["42"]\n', ""),
        is_complete=lambda document: "allow_from" not in document["plugins"]["qq"],
    )

    assert result == _MIGRATED
    assert path.read_text(encoding="utf-8").startswith("# 用户注释")
