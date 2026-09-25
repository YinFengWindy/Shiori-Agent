"""Writes a one-time config migration back to ``config.toml``, keeping comments.

Every startup config migration (built-in channel tables, default-disabled
plugins, channel ``allow_from`` removal) shares one policy: splice the change
into the user's TOML text so formatting and comments survive; when the line
scanner cannot express it (inline tables, dotted keys, a conflicting form) or
the spliced text does not parse to the intended result, rewrite the whole file
from the structural result, trading comments for correctness.
"""

from __future__ import annotations

import logging
import tomllib
from collections.abc import Callable
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


def save_migrated_config(
    path: Path,
    migrated: dict[str, Any],
    splice: Callable[[str], str],
    *,
    is_complete: Callable[[dict[str, Any]], bool] | None = None,
) -> dict[str, Any]:
    """Persists ``migrated`` to ``path`` atomically and returns the reparsed document.

    ``splice`` edits the current file text. Only the expected splice failures
    fall back to rendering ``migrated``: ``UnlocatableTable`` (a table written
    as dotted keys or an inline table), spliced text that does not parse, or a
    parsed result ``is_complete`` rejects (by default it must equal
    ``migrated``). Any other exception is a bug and propagates.
    """
    # 局部导入：迁移只在升级后的首次启动命中，不让每次加载配置都拉入 TOML 编辑模块。
    from desktop_bridge.plugin_config_text import UnlocatableTable
    from infra.persistence.text_store import atomic_save_text
    from infra.persistence.toml_store import render_toml

    accept = is_complete or (lambda document: document == migrated)
    fallback_reason = ""
    text = ""
    try:
        text = splice(path.read_text(encoding="utf-8"))
    except UnlocatableTable as error:
        fallback_reason = f"无法定位要改写的表：{error}"
    if not fallback_reason:
        try:
            if not accept(tomllib.loads(text)):
                fallback_reason = "拼接结果与迁移结果不一致"
        except tomllib.TOMLDecodeError as error:
            fallback_reason = f"拼接后的文本无法解析：{error}"
    if fallback_reason:
        logger.warning(
            "配置迁移无法按文本改写 %s（%s），改为整体重写，文件中的注释会丢失",
            path,
            fallback_reason,
        )
        text = render_toml(migrated)
    atomic_save_text(path, text)
    return tomllib.loads(text)
