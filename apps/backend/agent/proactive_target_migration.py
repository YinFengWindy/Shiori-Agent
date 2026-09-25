"""``[proactive]`` 全局投递目标一次性删除（#399）。

主动推送改为每个角色勾选接收会话、每条消息按桌面在场与最近对话选出唯一目标，
``[proactive.target]`` 以及 ``[proactive]`` 根级的 ``default_channel`` /
``default_chat_id`` / ``default_role_id`` 不再有任何含义。

规则：

- 回执 ``_migrations.proactive_target_removed = true`` 表示已迁移过。没有回执时
  删除这些旧键（没有旧键也照样）并写回执；有回执时不再迁移。
- 迁移之后旧键再次出现（例如手工加回）不会被静默删除，而是由
  ``proactive_v2.config_loader.reject_removed_target_keys`` 在加载配置时报错。
- 新安装的配置复制自 ``config/examples/config.example.toml``，模板自带回执。

写回走 ``agent/config_migration_writer.py``：尽量保留用户 TOML 的格式和注释。
"""

from __future__ import annotations

import logging
import re
from copy import deepcopy
from pathlib import Path
from typing import Any

from agent.config_migration_writer import save_migrated_config
from proactive_v2.config_loader import REMOVED_TARGET_KEYS

logger = logging.getLogger(__name__)

RECEIPT_KEY = "proactive_target_removed"

# A ``[table]`` header line (not ``[[array]]``), capturing its dotted path.
_TABLE_HEADER = re.compile(r"^\s*\[\s*([^\[\]]+?)\s*\]\s*(#.*)?$")
# A single-line ``key = ...`` assignment of one removed ``[proactive]`` key.
_REMOVED_KEY_LINE = re.compile(
    r"^\s*(" + "|".join(map(re.escape, REMOVED_TARGET_KEYS)) + r")\s*="
)


def remove_proactive_target(path: Path, data: dict[str, Any]) -> dict[str, Any]:
    """Deletes the legacy global proactive target once, recording a receipt."""
    metadata = data.get("_migrations", {})
    if not isinstance(metadata, dict):
        raise ValueError("_migrations 必须是对象")
    receipt = metadata.get(RECEIPT_KEY, False)
    if not isinstance(receipt, bool):
        raise ValueError(f"_migrations.{RECEIPT_KEY} 必须是布尔值")
    if receipt:
        return data
    proactive = data.get("proactive")
    removed = (
        [key for key in REMOVED_TARGET_KEYS if key in proactive]
        if isinstance(proactive, dict)
        else []
    )
    migrated = deepcopy(data)
    for key in removed:
        del migrated["proactive"][key]
    migrated.setdefault("_migrations", {})[RECEIPT_KEY] = True

    # 局部导入：迁移只在升级后的首次启动命中，不让每次加载配置都拉入 TOML 文本编辑模块。
    from desktop_bridge.plugin_config_text import merge_table

    def splice(text: str) -> str:
        return merge_table(
            _splice_out_target(text) if removed else text,
            ["_migrations"],
            migrated["_migrations"],
        )

    result = save_migrated_config(path, migrated, splice)
    if removed:
        logger.info(
            "已删除 config.toml 中 [proactive] 的全局投递目标 %s；"
            "主动推送的接收会话改由各角色勾选",
            ", ".join(removed),
        )
    return result


def _splice_out_target(text: str) -> str:
    """Drops the ``[proactive.target]`` table and single-line removed keys of ``[proactive]``.

    Other forms (dotted ``proactive.target.x`` keys, multi-line values) are left
    in place; the writer then sees an incomplete result and rewrites the file.
    """
    # 局部导入：迁移只在升级后的首次启动命中。
    from desktop_bridge.plugin_config_text import remove_table

    lines = remove_table(text, ["proactive", "target"]).splitlines(keepends=True)
    kept: list[str] = []
    table: str | None = None
    for line in lines:
        header = _TABLE_HEADER.match(line)
        if header is not None:
            table = re.sub(r"\s*\.\s*", ".", header.group(1))
        elif table == "proactive" and _REMOVED_KEY_LINE.match(line):
            continue
        kept.append(line)
    return "".join(kept)
