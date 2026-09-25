"""默认停用的内置插件：升级用户保留原有启用状态的一次性迁移。

manifest 的 ``default_enabled: false`` 只决定 ``[plugins.<id>]`` **没有显式**
``enabled`` 时的状态。在此之前所有插件缺省即启用，所以对一份早于该默认值的
配置，「没有 ``enabled``」意味着用户一直在用这个插件；直接套用新默认值会在升级
后悄悄把它停用。

规则：

- 回执 ``_migrations.plugin_default_disabled`` 记录已经按新默认值处理过的插件 ID；
  列在里面的插件不再迁移，之后删掉 ``enabled`` 就按 manifest 默认值停用。
- 回执里没有的插件：表里没有 ``enabled`` 时写入 ``enabled = true``（保持升级前的
  行为），已有的显式 ``enabled`` 原样保留；然后补回执。
- 新安装的配置复制自 ``config/examples/config.example.toml``，模板自带完整回执，
  因此新用户直接得到 manifest 的默认值（停用）。

以后再有内置插件改成默认停用，把它的 ID 追加到 ``DEFAULT_DISABLED_PLUGINS``
并同步写进模板回执即可；已经处理过的插件不会被重复迁移。
"""

from __future__ import annotations

import logging
import tomllib
from copy import deepcopy
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

# manifest 声明 default_enabled: false 的内置插件，按改为默认停用的先后追加。
DEFAULT_DISABLED_PLUGINS: tuple[str, ...] = ("browser_use", "computer_use")
RECEIPT_KEY = "plugin_default_disabled"


def migrate_plugin_default_enabled(path: Path, data: dict[str, Any]) -> dict[str, Any]:
    """Pins pre-existing configs to ``enabled = true`` once per newly default-off plugin."""
    metadata = data.get("_migrations", {})
    if not isinstance(metadata, dict):
        raise ValueError("_migrations 必须是对象")
    receipts = metadata.get(RECEIPT_KEY, [])
    if not isinstance(receipts, list) or any(
        not isinstance(item, str) for item in receipts
    ):
        raise ValueError(f"_migrations.{RECEIPT_KEY} 必须是插件 ID 数组")
    pending = [
        plugin_id for plugin_id in DEFAULT_DISABLED_PLUGINS if plugin_id not in receipts
    ]
    if not pending:
        return data
    plugins = _as_dict(data.get("plugins"))
    to_enable = [
        plugin_id
        for plugin_id in pending
        if "enabled" not in _as_dict(plugins.get(plugin_id))
    ]
    migrated = deepcopy(data)
    for plugin_id in to_enable:
        migrated.setdefault("plugins", {}).setdefault(plugin_id, {})["enabled"] = True
    migrated.setdefault("_migrations", {})[RECEIPT_KEY] = [*receipts, *pending]

    # 局部导入：迁移只在升级后的首次启动命中，不让每次加载配置都拉入 TOML 文本编辑模块。
    from desktop_bridge.plugin_config_text import (
        PluginTableConflict,
        merge_plugin_table,
        merge_table,
    )
    from infra.persistence.text_store import atomic_save_text
    from infra.persistence.toml_store import render_toml

    # 文本编辑保留用户 TOML 的格式和注释；行扫描处理不了（内联表、点号键）或结果
    # 与结构化版本不一致时整体重写，代价是丢失注释（与渠道配置迁移相同的取舍）。
    text = path.read_text(encoding="utf-8")
    try:
        for plugin_id in to_enable:
            text = merge_plugin_table(text, plugin_id, migrated["plugins"][plugin_id])
        text = merge_table(text, ["_migrations"], migrated["_migrations"])
        spliced_ok = tomllib.loads(text) == migrated
    except (PluginTableConflict, ValueError, tomllib.TOMLDecodeError):
        spliced_ok = False
    if not spliced_ok:
        text = render_toml(migrated)
    atomic_save_text(path, text)
    if to_enable:
        logger.info(
            "插件 %s 改为默认停用；已为升级前的配置显式保留启用",
            ", ".join(to_enable),
        )
    return tomllib.loads(text)


def _as_dict(value: object) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}
