from __future__ import annotations

import logging
from pathlib import Path

logger = logging.getLogger(__name__)


def _resolve_legacy_directory(current: Path, legacy: Path, label: str) -> Path:
    # 已存在的 Shiori 数据优先，禁止自动合并或覆盖。
    if current.exists() or not legacy.exists():
        return current

    current.parent.mkdir(parents=True, exist_ok=True)
    legacy.rename(current)
    logger.info("已迁移%s: %s -> %s", label, legacy, current)
    return current


def resolve_default_workspace(home: Path | None = None) -> Path:
    """Resolve the Shiori workspace and migrate the legacy default when needed."""
    home_dir = home or Path.home()
    return _resolve_legacy_directory(
        home_dir / ".shiori" / "workspace",
        home_dir / ".akashic" / "workspace",
        "工作区",
    )


def resolve_ncatbot_dir(home: Path | None = None) -> Path:
    """Resolve the NcatBot runtime directory and migrate its legacy location."""
    home_dir = home or Path.home()
    return _resolve_legacy_directory(
        home_dir / ".shiori" / "ncatbot",
        home_dir / ".akashic" / "ncatbot",
        "NcatBot 目录",
    )


def resolve_legacy_workspace_file(workspace: Path, value: object) -> str:
    """Resolve an existing file moved from the legacy workspace into Shiori."""

    raw_path = str(value or "").strip()
    current_workspace = workspace.expanduser().resolve()
    if not raw_path or current_workspace.parent.name.casefold() != ".shiori":
        return raw_path

    legacy_workspace = (
        current_workspace.parent.parent / ".akashic" / current_workspace.name
    )
    try:
        relative_path = Path(raw_path).relative_to(legacy_workspace)
    except ValueError:
        return raw_path

    current_path = current_workspace / relative_path
    return str(current_path) if current_path.is_file() else raw_path
