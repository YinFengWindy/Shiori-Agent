"""Pure canonical plugin data paths; migration and persistence remain host-owned."""

from pathlib import Path, PurePosixPath, PureWindowsPath

PLUGIN_DATA_DIRNAME = "plugin-data"


def plugin_data_dir(workspace: Path, plugin_id: str) -> Path:
    """Returns the writable per-plugin data directory under the workspace."""
    if (
        not plugin_id
        or plugin_id in {".", ".."}
        or any(
            parser(plugin_id).name != plugin_id or parser(plugin_id).is_absolute()
            for parser in (PurePosixPath, PureWindowsPath)
        )
    ):
        raise ValueError(f"插件 ID 不能包含路径: {plugin_id!r}")
    return workspace / PLUGIN_DATA_DIRNAME / plugin_id
