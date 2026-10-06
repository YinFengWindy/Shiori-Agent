"""Native paths for deeply nested private environments without machine-wide changes."""

import os
from pathlib import Path, PureWindowsPath


def windows_extended_path(path: str) -> str:
    """Preserve absolute drive/UNC paths using Windows' extended-length namespace."""
    normalized = str(PureWindowsPath(path))
    if not PureWindowsPath(normalized).is_absolute():
        raise ValueError("Windows 环境路径必须为绝对路径")
    if normalized.startswith("\\\\?\\"):
        return normalized
    if normalized.startswith("\\\\"):
        return "\\\\?\\UNC\\" + normalized[2:]
    return "\\\\?\\" + normalized


def native_path(path: Path) -> Path:
    """Normalize an owned filesystem path for both host I/O and child Python prefixes."""
    absolute = path.absolute()
    return Path(windows_extended_path(str(absolute))) if os.name == "nt" else absolute


def environment_path(path: Path) -> str:
    """Keep third-party path joining in normal Win32 semantics, at the same location."""
    value = str(native_path(path))
    if value.startswith("\\\\?\\UNC\\"):
        return "\\\\" + value[8:]
    return value[4:] if value.startswith("\\\\?\\") else value
