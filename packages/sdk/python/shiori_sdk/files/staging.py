"""Validate a native file-picker result inside its caller's import namespace."""

from pathlib import Path


def staged_import_file(
    workspace: Path, namespace: str, source: str, *, suffix: str, max_bytes: int
) -> Path:
    """Resolve a bounded regular file without accepting symlinks or path escapes."""
    if Path(namespace).name != namespace or namespace in {"", ".", ".."}:
        raise ValueError("无效的导入命名空间")
    requested = Path(source)
    root = (workspace / "private_runtime" / "imports").resolve() / namespace
    if not requested.is_absolute() or ".." in requested.parts:
        raise ValueError("文件必须来自原生文件选择")
    canonical = requested.resolve(strict=True)
    if (
        root.resolve() != root
        or not canonical.is_relative_to(root)
        or requested.is_symlink()
    ):
        raise ValueError("文件必须来自原生文件选择")
    if not canonical.is_file() or canonical.suffix.lower() != suffix:
        raise ValueError(f"需要普通 {suffix} 文件")
    if canonical.stat().st_size > max_bytes:
        raise ValueError("文件超过大小限制")
    return canonical
