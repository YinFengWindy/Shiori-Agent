"""内置渠道配置一次性迁入渠道插件（#363）。

Telegram / QQ（NapCat）迁为插件后，``[channels.<name>]`` 改写为 ``[plugins.<name>]``，
渠道名与插件 id 相同，角色绑定和会话线程都按渠道名做键，所以只迁配置、不迁数据。

规则（与 #180 novelai 迁移同一思路，靠「旧表是否还在」判断是否迁移过）：

- 值取自 ``tomllib`` 原文，``${ENV}`` 占位符原样搬运，不会把解析后的密钥写进文件。
- 凭据字段为空的旧表（桌面端总会写出 ``token = ""``）直接删除，不生成插件表。
- 旧表 ``enabled = false`` 且插件表还没有 ``enabled`` 时写 ``enabled = false``；
  插件表已有的 ``enabled`` 始终保留。
- 插件表已有 ``enabled`` 以外的键时插件表优先，丢弃旧表并记 warning。
- 迁移后仍出现非空旧表（raw TOML 编辑、旧版渲染端）由
  :func:`reject_migrated_channel_tables` 直接报错；空旧表只忽略。
"""

from __future__ import annotations

import logging
import tomllib
from copy import deepcopy
from dataclasses import dataclass
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class LegacyChannelTable:
    """一个已迁为插件的内置渠道：``[channels.<name>]`` → ``[plugins.<name>]``。"""

    name: str
    # 判断旧表是否「非空」的凭据字段；为空视为未配置。
    credential: str
    # 原样搬进插件表的字段。
    keys: tuple[str, ...]


LEGACY_CHANNEL_TABLES: tuple[LegacyChannelTable, ...] = (
    # channel_name 不再迁移：插件只能注册 manifest 声明的 ``telegram``（#363 Q6）。
    LegacyChannelTable(name="telegram", credential="token", keys=("token",)),
    # 旧表没有 ws_uri/ws_token；它们是插件新开放的设置（#363 Q9）。
    LegacyChannelTable(
        name="qq",
        credential="bot_uin",
        keys=("bot_uin", "websocket_open_timeout_seconds"),
    ),
)


def migrate_legacy_channel_configs(path: Path, data: dict[str, Any]) -> dict[str, Any]:
    """Rewrites every legacy channel table into its plugin table once, then reparses."""
    channels = _as_dict(data.get("channels"))
    # 非表写法无从搬运，留给 reject_migrated_channel_tables 报错。
    pending = [
        table
        for table in LEGACY_CHANNEL_TABLES
        if isinstance(channels.get(table.name), dict)
    ]
    if not pending:
        return data
    # 局部导入：迁移路径很少命中，不让每次加载配置都拉入 TOML 文本编辑模块。
    from desktop_bridge.plugin_config_text import (
        PluginTableConflict,
        merge_plugin_table,
        remove_table,
    )
    from infra.persistence.text_store import atomic_save_text
    from infra.persistence.toml_store import render_toml

    # 文本编辑保留用户 TOML 的格式和注释；structural 是同一结果的结构化版本，
    # 行扫描处理不了（内联表、点号键）时用它整体重写，代价是丢失注释。
    text: str | None = path.read_text(encoding="utf-8")
    structural = deepcopy(data)
    for table in pending:
        values = _plugin_values(table, channels[table.name], data)
        if values is not None:
            structural.setdefault("plugins", {})[table.name] = values
            if text is not None:
                try:
                    text = merge_plugin_table(text, table.name, values)
                except PluginTableConflict:
                    text = None
        _as_dict(structural.get("channels")).pop(table.name, None)
        if text is not None:
            text = remove_table(text, ["channels", table.name])
    if text is None or _still_has_legacy(tomllib.loads(text), pending):
        text = render_toml(structural)
    atomic_save_text(path, text)
    names = ", ".join(table.name for table in pending)
    logger.info("已将 [channels.%s] 一次性迁移至对应渠道插件配置", names)
    return tomllib.loads(text)


def reject_migrated_channel_tables(data: dict[str, Any]) -> None:
    """Rejects a non-empty legacy table that re-appeared after the migration."""
    channels = _as_dict(data.get("channels"))
    for table in LEGACY_CHANNEL_TABLES:
        if table.name in channels and _has_credential(table, channels[table.name]):
            raise ValueError(
                f"配置项已迁移: [channels.{table.name}] → [plugins.{table.name}]"
            )


def _plugin_values(
    table: LegacyChannelTable, legacy_values: dict[str, Any], data: dict[str, Any]
) -> dict[str, Any] | None:
    """Returns the plugin table to write, or ``None`` when the old table is dropped."""
    if not _has_credential(table, legacy_values):
        return None
    channel_name = legacy_values.get("channel_name")
    if channel_name not in (None, "", table.name):
        logger.warning(
            "[channels.%s] 的自定义 channel_name=%r 不再支持，迁移后渠道名固定为 %s",
            table.name,
            channel_name,
            table.name,
        )
    existing = _as_dict(_as_dict(data.get("plugins")).get(table.name))
    if set(existing) - {"enabled"}:
        logger.warning(
            "[plugins.%s] 已有配置，丢弃旧的 [channels.%s]", table.name, table.name
        )
        return None
    values = {key: legacy_values[key] for key in table.keys if key in legacy_values}
    if "enabled" in existing:
        values["enabled"] = existing["enabled"]
    elif legacy_values.get("enabled") is False:
        values["enabled"] = False
    return values


def _has_credential(table: LegacyChannelTable, legacy: object) -> bool:
    if not isinstance(legacy, dict):
        # 非表写法无法按空表忽略，按非空处理以便报错。
        return True
    return bool(str(legacy.get(table.credential) or "").strip())


def _still_has_legacy(
    document: dict[str, Any], tables: list[LegacyChannelTable]
) -> bool:
    channels = _as_dict(document.get("channels"))
    return any(table.name in channels for table in tables)


def _as_dict(value: object) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}
