"""Desktop-pet RPC boundary for native-selected package staging."""

from pathlib import Path

_PACKAGE_NAMESPACE = "pet_codex_sprite-pets"
_MAX_PACKAGE_BYTES = 32 * 1024 * 1024


def resolve_package_import_source(workspace: Path, source: str) -> Path:
    """Requires a regular bounded ZIP inside this plugin's private import staging."""
    requested = Path(source)
    if not requested.is_absolute() or ".." in requested.parts:
        raise ValueError("桌宠包必须来自原生文件选择")
    imports = (workspace / "private_runtime" / "imports").resolve()
    staging = imports / _PACKAGE_NAMESPACE
    if staging.resolve() != staging:
        raise ValueError("桌宠包暂存目录越界")
    canonical = requested.resolve(strict=True)
    if not canonical.is_relative_to(staging) or requested.is_symlink():
        raise ValueError("桌宠包必须来自原生文件选择")
    if canonical.suffix.lower() != ".zip" or not canonical.is_file():
        raise ValueError("桌宠包必须是普通 ZIP 文件")
    if canonical.stat().st_size > _MAX_PACKAGE_BYTES:
        raise ValueError("桌宠包超过 32MB")
    return canonical
