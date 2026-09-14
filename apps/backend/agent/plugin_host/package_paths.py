"""Portable paths for package directories and zip member names."""

from __future__ import annotations

import re
from pathlib import Path, PurePosixPath

from agent.plugin_host.diagnostics import PackageContractError

_RESERVED = re.compile(r"(?:CON|PRN|AUX|NUL|COM[1-9]|LPT[1-9])(?:\..*)?", re.I)


def package_path(value: object, field: str) -> str:
    """Require a canonical relative POSIX path that is also safe on Windows."""
    if not isinstance(value, str) or not value:
        raise PackageContractError(
            "invalid_path", field, "Expected a package-relative path"
        )
    parts = value.split("/")
    if (
        any(
            part in {"", ".", ".."}
            or part.endswith((".", " "))
            or _RESERVED.fullmatch(part)
            or any(ord(char) < 32 or char in '\\:*?"<>|' for char in part)
            for part in parts
        )
        or PurePosixPath(value).is_absolute()
    ):
        raise PackageContractError(
            "invalid_path", field, "Unsafe package path", path=value
        )
    return value


def contained_file(root: Path, value: object, field: str) -> Path:
    """Resolve a required regular file without allowing links outside its package."""
    relative = package_path(value, field)
    candidate = root.joinpath(*relative.split("/"))
    try:
        resolved = candidate.resolve(strict=True)
        if not resolved.is_relative_to(root.resolve()):
            raise PackageContractError(
                "outside_package", field, "Path escapes package", path=relative
            )
        if not resolved.is_file():
            raise PackageContractError(
                "invalid_entry", field, "Expected a regular file", path=relative
            )
    except (OSError, RuntimeError) as exc:
        raise PackageContractError(
            "missing_file", field, str(exc), path=relative
        ) from exc
    return resolved
