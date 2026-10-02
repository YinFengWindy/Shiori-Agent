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
``legacy_plugin_root`` / 插件目录里的迁移候选压根不存在，``migrate_plugin_file``
只是静默地什么都不做。**这里的一次性迁移实际只覆盖开发者（``git pull`` 到本地
未被 gitignore 清理的旧文件）与便携形态，不要理解成"已经挽回了打包用户的历史
数据"——那部分数据在安装器那一步就已经丢了，这份迁移救不回来。**
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
import tomllib

from agent.plugin_host.kv import PluginKVStore
from shiori_sdk.storage import (
    plugin_data_dir,
)
from shiori_sdk.files.json import atomic_save_json
from shiori_sdk.files.text import atomic_save_text

logger = logging.getLogger(__name__)

_KV_FILENAME = "kv.json"
_LEGACY_KV_FILENAME = ".kv.json"


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
        text = source.read_text(encoding="utf-8")
        if filename.endswith(".toml"):
            tomllib.loads(text)
        atomic_save_text(target, text)
    if not remove_source:
        return target
    remove_migrated_source(source, plugin_id=plugin_id)
    return target


def remove_migrated_source(source: Path, *, plugin_id: str) -> None:
    """Removes only a successfully copied source; read-only installs may retain it."""
    try:
        source.unlink()
    except OSError:
        logger.warning("插件 %s 的旧文件删除失败，已忽略: %s", plugin_id, source)


def legacy_plugin_files(
    *,
    workspace: Path,
    plugin_id: str,
    plugin_dir: Path,
    filename: str,
    legacy_plugin_root: Path | None = None,
) -> list[Path]:
    """Orders old workspace overrides before package and pre-move package files."""
    candidates = [workspace / "plugins" / plugin_id / filename, plugin_dir / filename]
    if legacy_plugin_root is not None:
        candidates.extend(
            [
                legacy_plugin_root / plugin_id / "backend" / filename,
                legacy_plugin_root / plugin_id / filename,
            ]
        )
    return list(dict.fromkeys(candidates))


def open_plugin_kv(
    *,
    workspace: Path,
    plugin_id: str,
    plugin_dir: Path,
    legacy_plugin_root: Path | None = None,
) -> PluginKVStore:
    """Opens a plugin's KV store under the workspace, migrating legacy data once.

    workspace 必传：内核在 setup 前已对缺 workspace 的宿主报 HostServiceUnavailable，
    这里不存在退回写插件目录的路径（#209 的病根）。

    ``legacy_plugin_root`` 是插件包上移到仓库顶层之前的存放位置
    （``apps/backend/plugins``）。`.kv.json` 被 gitignore 覆盖，所以目录重命名
    经 git 落到本地时**不会**跟着搬——旧数据会留在那个位置，必须一并作为迁移来源。
    """

    candidates = [
        workspace / "plugins" / plugin_id / _KV_FILENAME,
        plugin_dir / _LEGACY_KV_FILENAME,
    ]
    if legacy_plugin_root is not None:
        candidates.append(legacy_plugin_root / plugin_id / _LEGACY_KV_FILENAME)
    target = migrate_plugin_file(
        workspace=workspace,
        plugin_id=plugin_id,
        filename=_KV_FILENAME,
        sources=candidates,
    )
    return PluginKVStore(target)
