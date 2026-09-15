"""Resolve memory plugins' legacy overrides without ever writing package code."""

from pathlib import Path

from bootstrap.paths import REPOSITORY_ROOT
from agent.plugin_host.plugin_data import legacy_plugin_files, migrate_plugin_file
from infra.persistence.text_store import atomic_save_text


def resolve_local_config(
    *,
    plugin_id: str,
    plugin_dir: Path,
    workspace: Path | None,
    default_text: str | None = None,
) -> Path:
    """Migrates a local override; ensure calls create defaults only in a workspace.

    A loader without a workspace is read-only, useful for inspecting an explicit
    legacy package. Ensuring storage requires a workspace, never a package fallback.
    """
    if workspace is None:
        if default_text is not None:
            raise RuntimeError("创建插件配置需要 workspace，不能写入插件目录")
        return plugin_dir / "config.local.toml"
    path = migrate_plugin_file(
        workspace=workspace,
        plugin_id=plugin_id,
        filename="config.local.toml",
        sources=legacy_plugin_files(
            workspace=workspace,
            plugin_id=plugin_id,
            plugin_dir=plugin_dir,
            filename="config.local.toml",
            legacy_plugin_root=REPOSITORY_ROOT / "apps/backend/plugins",
        ),
    )
    if default_text is not None and not path.exists():
        atomic_save_text(path, default_text)
    return path
