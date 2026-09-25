"""配置迁移的共享写回：能拼接就保留注释，拼不出来就整体重写。"""

from __future__ import annotations

import logging
import tomllib
from collections.abc import Callable
from pathlib import Path

import pytest

from agent.config_migration_writer import save_migrated_config
from desktop_bridge.plugin_config_text import PluginTableConflict, UnlocatableTable

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


def _raise(error: Exception) -> Callable[[str], str]:
    def splice(_text: str) -> str:
        raise error

    return splice


@pytest.mark.parametrize(
    "splice, reason",
    [
        (_raise(PluginTableConflict("qq")), "无法定位要改写的表"),
        (_raise(UnlocatableTable("Cannot locate table _migrations")), "无法定位"),
        (lambda text: text, "拼接结果与迁移结果不一致"),
        (lambda text: text + "[[broken", "拼接后的文本无法解析"),
    ],
)
def test_expected_splice_failure_rewrites_the_file_and_warns(
    tmp_path: Path,
    caplog: pytest.LogCaptureFixture,
    splice: Callable[[str], str],
    reason: str,
) -> None:
    path = _config(tmp_path)

    with caplog.at_level(logging.WARNING, logger="agent.config_migration_writer"):
        result = save_migrated_config(path, _MIGRATED, splice)

    assert result == _MIGRATED
    assert tomllib.loads(path.read_text(encoding="utf-8")) == _MIGRATED
    assert "# 用户注释" not in path.read_text(encoding="utf-8")
    [record] = caplog.records
    message = record.getMessage()
    assert str(path) in message and reason in message and "注释会丢失" in message


def test_unexpected_splice_error_propagates_and_leaves_the_file(
    tmp_path: Path,
) -> None:
    path = _config(tmp_path)

    # A plain ValueError is a bug in the splice, not an unlocatable table.
    with pytest.raises(ValueError, match="bug"):
        _ = save_migrated_config(path, _MIGRATED, _raise(ValueError("bug")))

    assert path.read_text(encoding="utf-8") == _ORIGINAL


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
