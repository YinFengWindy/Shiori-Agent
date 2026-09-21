"""Pinned native runtime resolution and private child-process environment."""

import os
from pathlib import Path
import platform
import sys

from agent.mcp.client import McpClient
from bootstrap.paths import resource_root


def resolve_driver() -> Path:
    """Resolves prepared or frozen files; never uses a global installation."""
    if sys.platform != "win32" or platform.machine().lower() not in {"amd64", "x86_64"}:
        raise RuntimeError("Computer Use 首版仅支持 Windows x64")
    root = resource_root() / "native" / "computer-use"
    for name in ("cua-driver.exe", "cua-driver-uia.exe"):
        if not (root / name).is_file():
            raise FileNotFoundError(
                f"Computer Use 运行组件缺失：{root / name}；开发环境请运行 pnpm prepare:computer-use，发行版请重新安装"
            )
    return root / "cua-driver.exe"


def driver_client(root: Path, executable: Path) -> McpClient:
    """Owns a direct stdio runtime and isolates all Driver config/state in plugin-data."""
    root.mkdir(parents=True, exist_ok=True)
    # Driver reads HOME/USERPROFILE directly, including saved config and updates.
    # Only the child receives these values; the host environment is untouched.
    env = {
        key: value
        for key, value in os.environ.items()
        if not key.upper().startswith("CUA_")
    }
    for key in ("HOME", "USERPROFILE", "APPDATA", "LOCALAPPDATA", "TEMP", "TMP"):
        env[key] = str(root)
    env.update(
        CUA_DRIVER_RS_TELEMETRY_ENABLED="0",
        CUA_DRIVER_TELEMETRY_HOME=str(root / "telemetry"),
        CUA_DRIVER_RS_UPDATE_CHECK="0",
    )
    return McpClient(
        "computer_use",
        [str(executable), "mcp", "--direct"],
        env=env,
        cwd=str(root),
        own_process_tree=True,
        inherit_env=False,
    )
