"""Resolve memory plugins' local overrides without ever writing package code."""

from pathlib import Path

from shiori_sdk.files.text import atomic_save_text
from shiori_sdk.storage import plugin_data_dir


def resolve_local_config(
    *,
    plugin_id: str,
    plugin_dir: Path,
    workspace: Path | None,
    default_text: str | None = None,
) -> Path:
    """Returns the workspace override; ensure calls create defaults only there.

    A loader without a workspace is read-only, useful for inspecting a package's
    own ``config.local.toml``. Ensuring storage requires a workspace.
    """
    if workspace is None:
        if default_text is not None:
            raise RuntimeError("创建插件配置需要 workspace，不能写入插件目录")
        return plugin_dir / "config.local.toml"
    path = plugin_data_dir(workspace, plugin_id) / "config.local.toml"
    if default_text is not None and not path.exists():
        atomic_save_text(path, default_text)
    return path
