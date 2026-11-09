"""Codex package ZIP and manifest validation."""

from __future__ import annotations

import json
import re
import zipfile
from pathlib import PurePosixPath

_ACTION_NAME_PATTERN = re.compile(r"^[a-z][a-z0-9_-]{0,63}$")
_ACTION_STATES = frozenset(
    {
        "idle",
        "running-right",
        "running-left",
        "waving",
        "jumping",
    }
)


def safe_relative_path(value: str) -> str:
    """Rejects absolute, parent-traversing and platform-specific ZIP paths."""
    path = PurePosixPath(value)
    if (
        not value
        or "\\" in value
        or ":" in value
        or path.is_absolute()
        or ".." in path.parts
        or path == "."
    ):
        raise ValueError("桌宠包路径不安全")
    return path.as_posix()


def archive_names(archive: zipfile.ZipFile) -> tuple[set[str], str]:
    """Validates ZIP member names and locates the package root."""
    names: set[str] = set()
    for entry in archive.infolist():
        if entry.is_dir():
            continue
        name = safe_relative_path(entry.filename)
        if name in names:
            raise ValueError("桌宠包包含重复路径")
        names.add(name)
    if "pet.json" in names:
        return names, ""
    roots = {
        PurePosixPath(name).parts[0]
        for name in names
        if len(PurePosixPath(name).parts) > 1
    }
    if len(roots) != 1:
        raise ValueError("桌宠包缺少 pet.json")
    root = next(iter(roots))
    logical_names = {
        PurePosixPath(name).relative_to(root).as_posix()
        for name in names
        if PurePosixPath(name).parts[0] == root
    }
    if "pet.json" not in logical_names:
        raise ValueError("桌宠包缺少 pet.json")
    return logical_names, root


def archive_entry(root: str, name: str) -> str:
    """Resolves a validated relative path inside its ZIP root."""
    return f"{root}/{name}" if root else name


def manifest(archive: zipfile.ZipFile, root: str) -> dict[str, object]:
    """Parses the package manifest and verifies required fields."""
    try:
        value = json.loads(
            archive.read(archive_entry(root, "pet.json")).decode("utf-8")
        )
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ValueError("桌宠包 pet.json 无效") from error
    if not isinstance(value, dict):
        raise ValueError("桌宠包 pet.json 必须是对象")
    for field in ("id", "displayName", "description", "spritesheetPath"):
        if not isinstance(value.get(field), str) or not str(value[field]).strip():
            raise ValueError(f"桌宠包 pet.json 缺少 {field}")
    return value


def manifest_actions(manifest: dict[str, object]) -> dict[str, str]:
    """Validates declared semantic actions against supported animations."""
    raw_actions = manifest.get("actions", {})
    if raw_actions is None:
        return {}
    if not isinstance(raw_actions, dict):
        raise ValueError("桌宠包 actions 必须是对象")
    actions: dict[str, str] = {}
    for raw_name, raw_state in raw_actions.items():
        if not isinstance(raw_name, str) or not _ACTION_NAME_PATTERN.fullmatch(
            raw_name
        ):
            raise ValueError("桌宠包动作名称无效")
        if not isinstance(raw_state, str) or raw_state not in _ACTION_STATES:
            raise ValueError("桌宠包动作状态无效")
        actions[raw_name] = raw_state
    return actions
