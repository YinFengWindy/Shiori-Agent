"""插件私有数据的落盘位置：workspace，而不是插件目录（issue #209）。

插件目录在打包形态下位于应用安装目录内——PyInstaller 经 ``--add-data`` 把
``plugins/`` 摊在 ``sys._MEIPASS``，electron-builder 再把整个 runtime 放进
``resources/runtime``。往那里写用户数据有两个后果：NSIS 升级会重装
``resources/``，数据每次升级即丢；用户若把应用装到 ``Program Files``，写入
直接因权限失败。

因此插件的私有状态统一落在 workspace 下，与会话库、角色、记忆、配置同处一地，
按插件分目录。**插件目录是代码，用户数据归 workspace。**

## 本文件里的迁移覆盖不到打包用户

issue #209 的前提就是「NSIS 升级会整体重装 ``resources/``」。也就是说，打包
形态下旧 kv／配置本来就已经被安装器删掉了——新版本首次启动时，下面这些
``legacy_plugin_root`` / 插件目录里的迁移候选压根不存在，``_migrate_legacy_json``
只是静默地什么都不做。**这里的一次性迁移实际只覆盖开发者（``git pull`` 到本地
未被 gitignore 清理的旧文件）与便携形态，不要理解成"已经挽回了打包用户的历史
数据"——那部分数据在安装器那一步就已经丢了，这份迁移救不回来。**
"""

from __future__ import annotations

import json
import logging
from pathlib import Path

from agent.plugin_host.kv import PluginKVStore
from infra.persistence.json_store import atomic_save_json

logger = logging.getLogger(__name__)

# workspace 下存放各插件私有数据的目录名
PLUGIN_DATA_DIRNAME = "plugin-data"
_KV_FILENAME = "kv.json"
_LEGACY_KV_FILENAME = ".kv.json"


def plugin_data_dir(workspace: Path, plugin_id: str) -> Path:
    """Returns the writable per-plugin data directory under the workspace."""

    return workspace / PLUGIN_DATA_DIRNAME / plugin_id


def migrate_plugin_file(
    *,
    workspace: Path,
    plugin_id: str,
    filename: str,
    sources: list[Path],
    remove_source: bool = True,
) -> Path:
    """Atomically migrate the first legacy file into the independent data root."""
    target = plugin_data_dir(workspace, plugin_id) / filename
    if target.exists():
        return target
    source = next((path for path in sources if path.exists()), None)
    if source is None:
        return target
    target.parent.mkdir(parents=True, exist_ok=True)
    if filename.endswith(".json"):
        atomic_save_json(target, json.loads(source.read_text(encoding="utf-8")))
    else:
        from infra.persistence.text_store import atomic_save_text

        atomic_save_text(target, source.read_text(encoding="utf-8"))
    if not remove_source:
        return target
    try:
        source.unlink()
    except OSError:
        logger.warning("插件 %s 的旧文件删除失败，已忽略: %s", plugin_id, source)
    return target


def open_plugin_kv(
    *,
    workspace: Path | None,
    plugin_id: str,
    plugin_dir: Path,
    legacy_plugin_root: Path | None = None,
) -> PluginKVStore:
    """Opens a plugin's KV store under the workspace, migrating legacy data once.

    宿主未提供 workspace 时直接报错，而不是退回写插件目录——那正是 #209 的
    病根，留一条静默回退等于把 bug 保留在最不容易被发现的路径上。

    ``legacy_plugin_root`` 是插件包上移到仓库顶层之前的存放位置
    （``apps/backend/plugins``）。`.kv.json` 被 gitignore 覆盖，所以目录重命名
    经 git 落到本地时**不会**跟着搬——旧数据会留在那个位置，必须一并作为迁移来源。
    """

    if workspace is None:
        raise RuntimeError(
            f"插件 {plugin_id} 需要 kv 存储，但宿主未提供 workspace；"
            "插件数据不能写入插件目录（见 issue #209）"
        )
    target = plugin_data_dir(workspace, plugin_id) / _KV_FILENAME
    candidates = [plugin_dir / _LEGACY_KV_FILENAME]
    if legacy_plugin_root is not None:
        candidates.append(legacy_plugin_root / plugin_id / _LEGACY_KV_FILENAME)
    _migrate_legacy_json(candidates, target, plugin_id=plugin_id, description="kv 数据")
    return PluginKVStore(target)


def _migrate_legacy_json(
    candidates: list[Path], target: Path, *, plugin_id: str, description: str
) -> None:
    """一次性、原子地把 ``candidates`` 中第一个存在的 JSON 文件迁移到 ``target``。

    不搬的话，已在使用 kv 的插件（例如 novelai 的自动 CG 冷却与场景去重）
    会在升级到本版本时状态归零——对 novelai
    而言意味着去重失效、同一场景被重复生图。

    按 ``candidates`` 顺序取第一个存在的来源。**只删除真正被迁移的那一个
    source**，其余候选原样保留：迁移成功后 ``target.exists()`` 会让函数直接
    早退，其余候选之后永远不会再被读取，删除它们没有任何收益，只会把用户的
    另一份数据静默销毁。

    写入经临时文件 + 原子替换（复用 ``json_store.atomic_save_json``）：写到一半
    失败不会留下半截 ``target``；source 的删除在写入成功之后才发生，因此写入
    失败时 source 依然完整保留，不会出现"目标已存在但是损坏、旧数据也已经不
    在"的永久损坏态。
    """

    if target.exists():
        return
    source = next((path for path in candidates if path.exists()), None)
    if source is None:
        return
    data = json.loads(source.read_text(encoding="utf-8"))
    atomic_save_json(target, data)
    logger.info("插件 %s 的%s已从 %s 迁移到 %s", plugin_id, description, source, target)
    try:
        source.unlink()
    except OSError as error:
        # 打包形态下插件目录可能只读。数据已经落到新位置，旧文件残留无害且
        # 不再被读取，不值得为删不掉它而让插件加载失败。
        logger.warning(
            "插件 %s 的旧%s文件删除失败，已忽略: %s", plugin_id, description, error
        )
