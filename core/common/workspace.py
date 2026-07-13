from __future__ import annotations

import logging
from pathlib import Path

logger = logging.getLogger(__name__)


def resolve_default_workspace(home: Path | None = None) -> Path:
    """Resolve the Shiori workspace and migrate the legacy default when needed."""
    home_dir = home or Path.home()
    workspace = home_dir / ".shiori" / "workspace"
    legacy_workspace = home_dir / ".akashic" / "workspace"
    # 已存在的 Shiori 数据优先，禁止自动合并或覆盖。
    if workspace.exists() or not legacy_workspace.exists():
        return workspace

    workspace.parent.mkdir(parents=True, exist_ok=True)
    legacy_workspace.rename(workspace)
    logger.info("已迁移工作区: %s -> %s", legacy_workspace, workspace)
    return workspace
