"""Writes a one-time config migration back to ``config.toml``, keeping comments.

Every startup config migration (built-in channel tables, default-disabled
plugins, channel ``allow_from`` removal) shares one policy: splice the change
into the user's TOML text so formatting and comments survive; when the line
scanner cannot express it (inline tables, dotted keys, a conflicting form) or
the spliced text does not parse to the intended result, rewrite the whole file
from the structural result, trading comments for correctness.
"""

from __future__ import annotations

import tomllib
from collections.abc import Callable
from pathlib import Path
from typing import Any


def save_migrated_config(
    path: Path,
    migrated: dict[str, Any],
    splice: Callable[[str], str],
    *,
    is_complete: Callable[[dict[str, Any]], bool] | None = None,
) -> dict[str, Any]:
    """Persists ``migrated`` to ``path`` atomically and returns the reparsed document.

    ``splice`` edits the current file text; it may raise ``ValueError``
    (``PluginTableConflict`` included) when it cannot locate what to edit.
    ``is_complete`` judges the parsed spliced text; by default it must equal
    ``migrated`` exactly. Either failure falls back to rendering ``migrated``.
    """
    # 局部导入：迁移只在升级后的首次启动命中，不让每次加载配置都拉入 TOML 写出模块。
    from infra.persistence.text_store import atomic_save_text
    from infra.persistence.toml_store import render_toml

    accept = is_complete or (lambda document: document == migrated)
    text: str | None
    try:
        text = splice(path.read_text(encoding="utf-8"))
        # tomllib.TOMLDecodeError is a ValueError as well.
        if not accept(tomllib.loads(text)):
            text = None
    except ValueError:
        text = None
    if text is None:
        text = render_toml(migrated)
    atomic_save_text(path, text)
    return tomllib.loads(text)
