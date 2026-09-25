"""渠道插件配置里的 ``allow_from`` 白名单一次性删除（#398）。

谁能和角色说话只由角色绑定决定：私聊绑定的对方即会话本身，群聊绑定默认放行
所有成员、只忽略黑名单成员。qq / qqbot / telegram 插件不再按白名单过滤，旧配置
里的 ``allow_from``（qqbot 旧版群配置 ``groups`` 里的也算）没有任何含义，启动时
从 ``[plugins.<id>]`` 删除；靠「旧键是否还在」判断是否迁移过，删完即不再命中。

文本编辑保留用户 TOML 的格式和注释；行扫描处理不了（内联表、点号键）或结果与
结构化版本不一致时整体重写，代价是丢失注释（与渠道配置迁移相同的取舍）。
"""

from __future__ import annotations

import logging
import tomllib
from copy import deepcopy
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

# 曾经提供插件级白名单的渠道插件。
ALLOWLIST_PLUGINS: tuple[str, ...] = ("qq", "qqbot", "telegram")
# qqbot 的 pydantic 模型接受驼峰别名，两种写法都删。
_ALLOWLIST_KEYS = ("allow_from", "allowFrom")


def remove_channel_allowlists(path: Path, data: dict[str, Any]) -> dict[str, Any]:
    """Deletes every legacy ``allow_from`` from channel plugin tables, then reparses."""
    plugins = _as_dict(data.get("plugins"))
    migrated = deepcopy(data)
    changed: list[str] = []
    for plugin_id in ALLOWLIST_PLUGINS:
        table = plugins.get(plugin_id)
        if not isinstance(table, dict):
            continue
        cleaned = _without_allowlists(table)
        if cleaned != table:
            migrated["plugins"][plugin_id] = cleaned
            changed.append(plugin_id)
    if not changed:
        return data

    # 局部导入：迁移只在升级后的首次启动命中，不让每次加载配置都拉入 TOML 文本编辑模块。
    from desktop_bridge.plugin_config_text import (
        PluginTableConflict,
        merge_plugin_table,
    )
    from infra.persistence.text_store import atomic_save_text
    from infra.persistence.toml_store import render_toml

    text = path.read_text(encoding="utf-8")
    try:
        for plugin_id in changed:
            text = merge_plugin_table(text, plugin_id, migrated["plugins"][plugin_id])
        spliced_ok = tomllib.loads(text) == migrated
    except (PluginTableConflict, ValueError, tomllib.TOMLDecodeError):
        spliced_ok = False
    if not spliced_ok:
        text = render_toml(migrated)
    atomic_save_text(path, text)
    logger.info(
        "已删除插件 %s 配置里的 allow_from 白名单；访问控制改由角色绑定的群黑名单负责",
        ", ".join(changed),
    )
    return tomllib.loads(text)


def _without_allowlists(table: dict[str, Any]) -> dict[str, Any]:
    """Returns ``table`` minus its ``allow_from`` keys, also inside qqbot ``groups``."""
    cleaned = _drop_allowlist_keys(table)
    groups = cleaned.get("groups")
    if isinstance(groups, list):
        cleaned["groups"] = [
            _drop_allowlist_keys(group) if isinstance(group, dict) else group
            for group in groups
        ]
    return cleaned


def _drop_allowlist_keys(values: dict[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in values.items() if key not in _ALLOWLIST_KEYS}


def _as_dict(value: object) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}
