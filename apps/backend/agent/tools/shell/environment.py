"""Shell 子进程环境发现与 PATH 组装。"""

from __future__ import annotations

import os
from pathlib import Path


def _shell_env() -> dict[str, str]:
    env = os.environ.copy()
    _prepend_existing_path_entries(env, _discover_user_path_entries(env))
    return env


def _discover_user_path_entries(env: dict[str, str]) -> list[Path]:
    home_text = env.get("HOME")
    if not home_text:
        return []
    home = Path(home_text).expanduser()
    nvm_dir = Path(env.get("NVM_DIR") or home / ".nvm").expanduser()
    entries = [home / ".local" / "bin"]
    nvm_bin = env.get("NVM_BIN")
    if nvm_bin:
        entries.append(Path(nvm_bin).expanduser())
    entries.extend(_discover_nvm_node_bins(nvm_dir))
    return entries


def _discover_nvm_node_bins(nvm_dir: Path) -> list[Path]:
    node_root = nvm_dir / "versions" / "node"
    try:
        version_dirs = [p for p in node_root.iterdir() if p.is_dir()]
    except OSError:
        return []
    return [
        version_dir / "bin"
        for version_dir in sorted(
            version_dirs,
            key=lambda p: _node_version_key(p.name),
            reverse=True,
        )
        if (version_dir / "bin").is_dir()
    ]


def _node_version_key(version: str) -> tuple[int, int, int]:
    parts = version.removeprefix("v").split(".")
    nums: list[int] = []
    for part in parts[:3]:
        nums.append(int(part) if part.isdigit() else 0)
    while len(nums) < 3:
        nums.append(0)
    return (nums[0], nums[1], nums[2])


def _prepend_existing_path_entries(env: dict[str, str], entries: list[Path]) -> None:
    current = [p for p in env.get("PATH", "").split(os.pathsep) if p]
    seen = set(current)
    prepend: list[str] = []
    for entry in entries:
        text = str(entry)
        if text in seen or not entry.is_dir():
            continue
        prepend.append(text)
        seen.add(text)
    env["PATH"] = os.pathsep.join([*prepend, *current])
