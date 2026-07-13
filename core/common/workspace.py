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
