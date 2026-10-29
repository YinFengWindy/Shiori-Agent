"""The plugin-table TOML editor shared by the startup config migrations.

``desktop_bridge/plugin_config_text.py`` is loaded from its file under one
module name, so the migrations reuse the desktop's comment-preserving editor
without importing the ``desktop_bridge`` package before the config is read.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from typing import Any

_EDITOR_MODULE = "_shiori_migration_plugin_config_text"


def plugin_table_editor() -> Any:
    """The loaded ``plugin_config_text`` module, loaded once per process."""
    cached = sys.modules.get(_EDITOR_MODULE)
    if cached is not None:
        return cached
    path = (
        Path(__file__).resolve().parents[1] / "desktop_bridge" / "plugin_config_text.py"
    )
    spec = importlib.util.spec_from_file_location(_EDITOR_MODULE, path)
    if spec is None or spec.loader is None:
        raise ImportError(f"无法加载 TOML 表编辑器: {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[_EDITOR_MODULE] = module
    spec.loader.exec_module(module)
    return module
