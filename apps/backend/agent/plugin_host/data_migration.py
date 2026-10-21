"""Host side of the SDK ``PrivateStorage.migrate_data`` contract."""

from __future__ import annotations

from pathlib import Path

from shiori_sdk.storage import plugin_data_dir


def migrate_private_data(
    workspace: Path, plugin_id: str, name: str, source: Path
) -> Path:
    """Return the plugin-owned destination for ``name``; ``source`` is not read.

    Released 0.5.x data already lives under the plugin data root. The SDK keeps
    this call for 3.1.x plugins, so the host only resolves the target.
    """
    _ = source
    if not name or Path(name).name != name or name in {".", ".."}:
        raise ValueError("插件数据名称必须是单个路径段")
    return plugin_data_dir(workspace, plugin_id) / name
