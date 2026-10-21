"""插件私有数据的落盘位置：workspace，而不是插件目录（issue #209）。

插件目录在打包形态下位于应用安装目录内，NSIS 升级会整体重装 ``resources/``，
装在 ``Program Files`` 时还没有写权限。因此插件的私有状态统一落在 workspace 下，
按插件分目录。**插件目录是代码，用户数据归 workspace。**
"""

from __future__ import annotations

from pathlib import Path

from agent.plugin_host.kv import PluginKVStore
from shiori_sdk.storage import plugin_data_dir

_KV_FILENAME = "kv.json"


def open_plugin_kv(*, workspace: Path, plugin_id: str) -> PluginKVStore:
    """Opens a plugin's KV store under the workspace data root.

    workspace 必传：内核在 setup 前已对缺 workspace 的宿主报 HostServiceUnavailable，
    这里不存在退回写插件目录的路径（#209 的病根）。
    """
    return PluginKVStore(plugin_data_dir(workspace, plugin_id) / _KV_FILENAME)
