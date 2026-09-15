"""Content identities for explicit package trust; no package code is evaluated."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path

from agent.plugin_host.diagnostics import PackageContractError


@dataclass(frozen=True)
class PackageContent:
    """Identity of published files, with verified Python source bytes for imports."""

    fingerprint: str
    sources: dict[str, bytes]
    directory: str
    hashes: dict[str, str]


def inspect_package_content(directory: Path) -> PackageContent:
    """Hash names and bytes, binding approval to the real directory and all content.

    Python caches are generated runtime data, not distributable executable input.
    External imports consume only the source bytes captured here, never pyc files.
    """
    try:
        root = directory.resolve(strict=True)
        files: list[tuple[str, str]] = []
        sources: dict[str, bytes] = {}

        def visit(folder: Path) -> None:
            for path in sorted(folder.iterdir()):
                resolved = path.resolve(strict=True)
                if path.is_symlink() or resolved != path.absolute():
                    raise PackageContractError(
                        "unsafe_package_link",
                        "trust",
                        "信任的插件包不能包含链接",
                        path=str(path),
                    )
                if path.is_dir():
                    visit(path)
                    continue
                if path.is_file() and path.suffix in {".pyc", ".pyo"}:
                    continue
                before = path.stat()
                if not path.is_file():
                    raise PackageContractError(
                        "invalid_entry", "trust", "插件包含非普通文件"
                    )
                data = path.read_bytes()
                after = path.stat()
                if (before.st_ino, before.st_size, before.st_mtime_ns) != (
                    after.st_ino,
                    after.st_size,
                    after.st_mtime_ns,
                ):
                    raise PackageContractError(
                        "package_changed", "trust", "插件内容正在变化，请重启后重试"
                    )
                files.append(
                    (
                        path.relative_to(root).as_posix(),
                        hashlib.sha256(data).hexdigest(),
                    )
                )
                if path.suffix == ".py":
                    sources[str(resolved)] = data

        visit(root)
        encoded = json.dumps(
            [str(root), files], ensure_ascii=False, separators=(",", ":")
        ).encode("utf-8")
        return PackageContent(
            hashlib.sha256(encoded).hexdigest(), sources, str(root), dict(files)
        )
    except (OSError, RuntimeError) as exc:
        raise PackageContractError(
            "package_unavailable", "trust", str(exc), path=str(directory)
        ) from exc
