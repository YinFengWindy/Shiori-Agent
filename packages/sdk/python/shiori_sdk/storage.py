"""Pure canonical plugin data paths; migration and persistence remain host-owned."""

from pathlib import Path, PurePosixPath, PureWindowsPath
from typing import Protocol

PLUGIN_DATA_DIRNAME = "plugin-data"


class KeyValueStore(Protocol):
    """Opaque plugin-owned JSON values retained across generations."""

    def get(self, key: str, default: object = None) -> object: ...
    def set(self, key: str, value: object) -> None: ...


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
